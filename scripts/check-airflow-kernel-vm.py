"""Boot a disposable KVM guest and exercise the real systemd reconciliation unit."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tarfile
import time
import urllib.request
from pathlib import Path

VM = Path('/vm')
PROOF = Path('/proof')
SOURCE = Path('/source')
BASE_URL = 'https://cloud-images.ubuntu.com/noble/current/'


def run(*args: str, timeout=300, data=None) -> str:
    result = subprocess.run(args, input=data, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError('Command failed: ' + ' '.join(args[:2]) + '\n' + result.stderr[-1500:])
    return result.stdout


def ssh(command: str, timeout=600) -> str:
    return run('ssh', '-i', str(VM / 'client'), '-p', '2222', '-o', 'BatchMode=yes',
               '-o', 'ConnectTimeout=60', '-o', 'StrictHostKeyChecking=yes', '-o', 'UpdateHostKeys=no',
               '-o', 'UserKnownHostsFile=' + str(VM / 'known_hosts'), 'ubuntu@127.0.0.1', command,
               timeout=timeout)


def copy_to_guest(path: Path, target: str) -> None:
    run('scp', '-i', str(VM / 'client'), '-P', '2222', '-o', 'BatchMode=yes',
        '-o', 'StrictHostKeyChecking=yes', '-o', 'UpdateHostKeys=no',
        '-o', 'UserKnownHostsFile=' + str(VM / 'known_hosts'), str(path),
        'ubuntu@127.0.0.1:' + target, timeout=1200)


def wait_guest(previous_boot: str | None = None) -> str:
    until = time.monotonic() + 900
    while time.monotonic() < until:
        try:
            boot = ssh('cat /proc/sys/kernel/random/boot_id', timeout=90).strip()
            if boot and boot != previous_boot:
                return boot
        except (RuntimeError, subprocess.TimeoutExpired):
            pass
        time.sleep(3)
    raise TimeoutError('Guest boot/SSH deadline exceeded')


def setup(architecture='amd64', memory_mib=4096, cpus=4, hostname='yunesa-kernel-proof') -> None:
    VM.chmod(0o700)
    for key in ('client', 'host'):
        if not (VM / key).exists():
            run('ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(VM / key))
    (VM / 'known_hosts').write_text('[127.0.0.1]:2222 ' + (VM / 'host.pub').read_text())
    sums = urllib.request.urlopen(BASE_URL + 'SHA256SUMS', timeout=60).read().decode()
    image = f'noble-server-cloudimg-{architecture}.img'
    checksum = next(line.split()[0] for line in sums.splitlines() if line.split()[-1].lstrip('*') == image)
    base = VM / 'base.img'
    if not base.exists():
        with urllib.request.urlopen(BASE_URL + image, timeout=120) as response, base.open('wb') as stream:
            while chunk := response.read(8 * 1024 * 1024):
                stream.write(chunk)
    assert hashlib.file_digest(base.open('rb'), 'sha256').hexdigest() == checksum
    (PROOF / 'cloud-image.json').write_text(json.dumps({'url': BASE_URL + image, 'sha256': checksum}, indent=2))
    if (VM / 'guest.qcow2').exists():
        raise RuntimeError('Refusing to replace an existing guest disk')
    run('qemu-img', 'create', '-f', 'qcow2', '-F', 'qcow2', '-b', str(base), str(VM / 'guest.qcow2'), '30G')
    private = '\n'.join('    ' + line for line in (VM / 'host').read_text().splitlines())
    config = f'''#cloud-config
hostname: {hostname}
ssh_pwauth: false
disable_root: true
ssh_authorized_keys:
  - {(VM / 'client.pub').read_text().strip()}
ssh_keys:
  ed25519_private: |
{private}
  ed25519_public: {(VM / 'host.pub').read_text().strip()}
package_update: true
packages:
  - docker.io
  - docker-compose-v2
  - python3
runcmd:
  - [systemctl, enable, --now, docker]
'''
    (VM / 'user-data').write_text(config)
    (VM / 'user-data').chmod(0o600)
    (VM / 'meta-data').write_text(f'instance-id: {hostname}-20261108\nlocal-hostname: {hostname}\n')
    run('cloud-localds', str(VM / 'seed.img'), str(VM / 'user-data'), str(VM / 'meta-data'))
    start_guest(architecture, memory_mib, cpus, hostname)


def start_guest(architecture: str, memory_mib: int, cpus: int, hostname: str,
                wait_cloud_init: bool = True) -> None:
    if architecture == 'arm64':
        machine = ['qemu-system-aarch64', '-machine', 'virt', '-accel', 'tcg,thread=multi',
                   '-cpu', 'neoverse-n1', '-bios', '/usr/share/qemu-efi-aarch64/QEMU_EFI.fd',
                   '-global', 'virtio-net-pci.romfile=']
    elif architecture == 'amd64':
        machine = ['qemu-system-x86_64', '-accel', 'kvm', '-cpu', 'host']
    else:
        raise ValueError('Unsupported local guest architecture')
    run(*machine, '-name', hostname,
        '-m', str(memory_mib), '-smp', str(cpus), '-drive', f'file={VM}/guest.qcow2,if=virtio,format=qcow2',
        '-drive', f'file={VM}/seed.img,if=virtio,format=raw', '-nic', 'user,model=virtio-net-pci,hostfwd=tcp:0.0.0.0:2222-:22',
        '-display', 'none', '-serial', 'file:' + str(VM / 'serial.log'), '-daemonize',
        '-pidfile', str(VM / 'qemu.pid'))
    boot = wait_guest()
    if wait_cloud_init:
        ssh('sudo cloud-init status --wait', timeout=1500)
    print('VM_INITIAL_BOOT=' + boot, flush=True)


def guest(action: str) -> dict:
    output = ssh('sudo python3 /source/scripts/check-airflow-kernel-guest.py ' + action, timeout=1200)
    marker = 'KERNEL_RESULT='
    if marker not in output:
        raise RuntimeError('Guest returned no structured result')
    value = json.loads(output.rsplit(marker, 1)[1])
    (PROOF / (action + '.json')).write_text(json.dumps(value, indent=2))
    print('KERNEL_PHASE=' + action, flush=True)
    return value


def reboot(old_boot: str) -> str:
    try:
        ssh('sudo systemctl reboot', timeout=15)
    except RuntimeError as error:
        if 'Connection' not in str(error) and 'closed' not in str(error):
            raise
    return wait_guest(old_boot)


def verify() -> None:
    archive = PROOF / 'source.tar'
    with tarfile.open(archive, 'w') as stream:
        for name in ('docker-compose.prod.yml', 'docker/yunesa-airflow-reconcile.service',
                     'scripts/airflow_operations.py', 'scripts/yunesa-airflow.sh',
                     'scripts/check-airflow-kernel-guest.py', 'orchestration/yunesa_airflow'):
            stream.add(SOURCE / name, arcname=name, filter=lambda item: None if '__pycache__' in item.name else item)
    copy_to_guest(archive, '/tmp/source.tar')
    ssh('sudo mkdir /source && sudo tar -xf /tmp/source.tar -C /source')
    copy_to_guest(PROOF / 'images.tar', '/tmp/images.tar')
    ssh('sudo docker load -i /tmp/images.tar >/tmp/image-load.log && sudo rm /tmp/images.tar', timeout=1500)
    initial = guest('prepare')
    off_boot = reboot(initial['boot_id'])
    off = guest('off-boot')
    assert off['boot_id'] == off_boot
    before_on = guest('arm-on')
    on_boot = reboot(off_boot)
    blocked = guest('blocked-on-boot')
    assert blocked['boot_id'] == on_boot and blocked['gate_boot_id'] == before_on['boot_id']
    recovered = guest('release-on')
    assert recovered['boot_id'] == on_boot
    guest('arm-failure')
    failure_boot = reboot(on_boot)
    failed = guest('failed-boot')
    assert failed['boot_id'] == failure_boot
    retry = guest('release-failure')
    assert retry['boot_id'] == failure_boot
    guest('arm-off')
    final_boot = reboot(failure_boot)
    final = guest('final-off-boot')
    assert final['boot_id'] == final_boot
    result = {'boot_ids': [initial['boot_id'], off_boot, on_boot, failure_boot, final_boot],
              'off': off, 'blocked_on': blocked, 'on': recovered, 'unit_failure': failed,
              'automatic_retry': retry, 'final_off': final, 'platform': 'linux/amd64 KVM'}
    assert len(set(result['boot_ids'])) == 5
    (PROOF / 'result.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=('setup', 'verify', 'shutdown'))
    args = parser.parse_args()
    if args.phase == 'setup':
        setup()
    elif args.phase == 'verify':
        verify()
    else:
        ssh('sudo systemctl poweroff', timeout=20)


if __name__ == '__main__':
    main()
