"""Render watchdog inputs and supervise an already-created disposable fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path

from airflow_capacity_session import Session, schedule_request, termination_policy, trust_policy, watchdog_units

ALLOWED = {
    ('sts', 'get-caller-identity'), ('ec2', 'describe-instances'), ('ec2', 'describe-instance-attribute'),
    ('ec2', 'terminate-instances'), ('ec2', 'describe-volumes'), ('ec2', 'describe-network-interfaces'),
    ('ec2', 'describe-addresses'),
    ('ec2', 'describe-security-groups'), ('ec2', 'delete-security-group'),
    ('ec2', 'describe-key-pairs'), ('ec2', 'delete-key-pair'),
    ('iam', 'get-role'), ('iam', 'get-role-policy'), ('iam', 'delete-role-policy'), ('iam', 'delete-role'),
    ('scheduler', 'get-schedule'), ('scheduler', 'delete-schedule'),
}


class AwsError(RuntimeError):
    def __init__(self, code: str, operation: str):
        super().__init__(operation + ' failed (' + code + ')')
        self.code = code


class AwsCli:
    def __init__(self, region: str):
        self.region = region

    def call(self, service: str, action: str, payload: dict) -> dict:
        if (service, action) not in ALLOWED:
            raise ValueError('AWS operation is outside the controller allowlist')
        with tempfile.TemporaryDirectory(prefix='yunesa-capacity-') as directory:
            path = Path(directory) / 'request.json'
            path.write_text(json.dumps(payload), encoding='utf-8')
            result = subprocess.run(['aws', service, action, '--region', self.region,
                '--cli-input-json', 'file://' + str(path), '--output', 'json', '--no-cli-pager',
                '--cli-connect-timeout', '5', '--cli-read-timeout', '5'],
                capture_output=True, text=True, timeout=20, env={**os.environ, 'AWS_MAX_ATTEMPTS': '1'})
        if result.returncode:
            match = re.search(r'\(([A-Za-z0-9.]+)\)', result.stderr)
            raise AwsError(match.group(1) if match else 'CliFailure', service + '/' + action)
        return json.loads(result.stdout or '{}')


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False, encoding='utf-8') as stream:
        temporary = Path(stream.name)
        json.dump(value, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def verify_guest(lease: dict, session: Session, public_ip: str) -> None:
    config = lease['ssh']
    if config['host'] != public_ip:
        raise ValueError('SSH target differs from the observed fixture IP')
    code = f"""import hashlib,json,pathlib,subprocess
name={session.name!r}
values={{'active':subprocess.check_output(['systemctl','is-active',name+'.timer'],text=True).strip()}}
for suffix in ['timer','service']:
 p=pathlib.Path('/etc/systemd/system')/(name+'.'+suffix)
 assert p.stat().st_uid==0 and p.stat().st_mode&0o022==0
 values[suffix]=hashlib.sha256(p.read_bytes()).hexdigest()
print(json.dumps(values))
"""
    result = subprocess.run(['ssh', '-F', os.devnull, '-i', config['key'],
        '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=10',
        '-o', 'UserKnownHostsFile=' + config['known_hosts'], 'ubuntu@' + public_ip, 'sudo python3 -'],
        input=code, capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise RuntimeError('Guest watchdog verification failed')
    value = json.loads(result.stdout)
    for name, content in watchdog_units(session).items():
        if value[name.rsplit('.', 1)[1]] != hashlib.sha256(content.encode()).hexdigest():
            raise ValueError('Guest watchdog source differs from the absolute deadline')
    if value['active'] != 'active':
        raise ValueError('Guest watchdog is inactive')


class Controller:
    def __init__(self, lease: dict, aws, receipt: Path, guest=verify_guest):
        self.lease = lease
        self.session = Session.read(lease)
        self.aws = aws
        self.receipt = receipt
        self.guest = guest
        self.result = {'session': self.session.session, 'instance_id': self.session.instance_id,
                       'events': [], 'cleanup_complete': False}
        if receipt.exists():
            previous = json.loads(receipt.read_text())
            if previous['session'] != self.session.session or previous['instance_id'] != self.session.instance_id:
                raise ValueError('Receipt belongs to another fixture')
            self.result = previous
        self.monotonic_end = time.monotonic() + max(0, self.session.expires_at - time.time())
        self.validate_resources()

    def validate_resources(self) -> None:
        for name, prefix in [('volume_id', 'vol'), ('eni_id', 'eni'), ('security_group_id', 'sg'), ('key_pair_id', 'key')]:
            if not re.fullmatch(prefix + r'-[a-f0-9]{8,17}', self.lease[name]):
                raise ValueError('Invalid recorded fixture resource ' + name)
        if self.lease['security_group_id'] == 'sg-0b1c3c340561e2436':
            raise ValueError('Production security group is protected')

    def event(self, phase: str, **values) -> None:
        self.result['events'].append({'at': time.time(), 'phase': phase, **values})
        write_json(self.receipt, self.result)

    def instance(self) -> dict | None:
        if self.aws.call('sts', 'get-caller-identity', {})['Account'] != self.session.account_id:
            raise ValueError('AWS account differs from the fixture lease')
        try:
            response = self.aws.call('ec2', 'describe-instances', {'InstanceIds': [self.session.instance_id]})
        except AwsError as error:
            if error.code == 'InvalidInstanceID.NotFound':
                return None
            raise
        items = [item for group in response['Reservations'] for item in group['Instances']]
        if len(items) != 1:
            raise ValueError('Expected exactly one fixture instance')
        item = items[0]
        self.session.check_tags(item.get('Tags', []))
        self.session.check_identity({'accountId': self.session.account_id, 'region': self.session.region,
            'instanceId': item['InstanceId'], 'instanceType': item['InstanceType'],
            'architecture': item['Architecture'], 'imageId': item['ImageId']})
        if item['ClientToken'] != self.session.session or item['KeyName'] != self.session.name:
            raise ValueError('Instance launch token or key differs from the fixture')
        launched = datetime.fromisoformat(item['LaunchTime'].replace('Z', '+00:00')).timestamp()
        if not -5 <= launched - self.session.started_at <= 120:
            raise ValueError('Instance launch time differs from the one-hour lease')
        if item['State']['Name'] in ('shutting-down', 'terminated'):
            return item
        disks = item['BlockDeviceMappings']
        interfaces = item['NetworkInterfaces']
        if (len(disks) != 1 or disks[0]['Ebs']['VolumeId'] != self.lease['volume_id']
                or disks[0]['Ebs']['DeleteOnTermination'] is not True):
            raise ValueError('Fixture volume identity or deletion policy differs')
        if len(interfaces) != 1 or interfaces[0]['NetworkInterfaceId'] != self.lease['eni_id']:
            raise ValueError('Fixture network interface differs')
        if {value['GroupId'] for value in item['SecurityGroups']} != {self.lease['security_group_id']}:
            raise ValueError('Fixture security group differs')
        addresses = self.aws.call('ec2', 'describe-addresses',
            {'Filters': [{'Name': 'network-interface-id', 'Values': [self.lease['eni_id']]}]})
        if addresses['Addresses']:
            raise ValueError('Fixture unexpectedly has a persistent Elastic IP')
        return item

    def check_ready(self) -> None:
        self.session.remaining(51)
        item = self.instance()
        if item is None or item['State']['Name'] != 'running':
            raise ValueError('Fixture is not running')
        shutdown = self.aws.call('ec2', 'describe-instance-attribute',
            {'InstanceId': self.session.instance_id, 'Attribute': 'instanceInitiatedShutdownBehavior'})
        if shutdown['InstanceInitiatedShutdownBehavior']['Value'] != 'terminate':
            raise ValueError('Guest shutdown must terminate the fixture')
        observed = self.aws.call('scheduler', 'get-schedule', {'Name': self.session.name, 'GroupName': 'default'})
        expected = schedule_request(self.session)
        for key in ('Name', 'GroupName', 'ScheduleExpression', 'ScheduleExpressionTimezone',
                    'FlexibleTimeWindow', 'State', 'ActionAfterCompletion', 'Target'):
            actual = observed[key]
            target = expected[key]
            if key == 'Target':
                actual = dict(actual)
                target = dict(target)
                actual['Input'] = json.loads(actual['Input'])
                target['Input'] = json.loads(target['Input'])
            if actual != target:
                raise ValueError('AWS watchdog read-back mismatch in ' + key)
        policy = self.aws.call('iam', 'get-role-policy', {'RoleName': self.session.name, 'PolicyName': 'terminate-fixture'})
        if policy['PolicyDocument'] != termination_policy(self.session):
            raise ValueError('Scheduler termination permission differs')
        role = self.aws.call('iam', 'get-role', {'RoleName': self.session.name})['Role']
        self.session.check_tags(role.get('Tags', []))
        if role['Arn'] != self.session.role_arn or role['AssumeRolePolicyDocument'] != trust_policy(self.session):
            raise ValueError('Scheduler role identity or trust differs')
        self.guest(self.lease, self.session, item['PublicIpAddress'])
        self.event('watchdogs_verified')

    def absent(self, action: str, payload: dict, code: str, field: str) -> bool:
        try:
            value = self.aws.call('ec2', action, payload)
        except AwsError as error:
            if error.code == code:
                return True
            raise
        return not value[field]

    def cleanup(self) -> None:
        self.result['cleanup_complete'] = False
        self.event('cleanup_started')
        item = self.instance()
        if item and item['State']['Name'] != 'terminated':
            self.aws.call('ec2', 'terminate-instances', {'InstanceIds': [self.session.instance_id]})
            self.event('termination_requested')
            until = time.monotonic() + 120
            while item and item['State']['Name'] != 'terminated':
                if time.monotonic() >= until:
                    raise TimeoutError('Fixture termination remains pending')
                time.sleep(1)
                item = self.instance()
        pending = []
        try:
            if not self.absent('describe-volumes', {'VolumeIds': [self.lease['volume_id']]},
                               'InvalidVolume.NotFound', 'Volumes'):
                pending.append('volume')
            if not self.absent('describe-network-interfaces', {'NetworkInterfaceIds': [self.lease['eni_id']]},
                               'InvalidNetworkInterfaceID.NotFound', 'NetworkInterfaces'):
                pending.append('eni')
        except (AwsError, RuntimeError, OSError, subprocess.SubprocessError) as error:
            pending.append(str(error))
        actions = [
            ('scheduler', 'get-schedule', {'Name': self.session.name, 'GroupName': 'default'}, 'ResourceNotFoundException'),
            ('ec2', 'describe-security-groups', {'GroupIds': [self.lease['security_group_id']]}, 'InvalidGroup.NotFound'),
            ('ec2', 'describe-key-pairs', {'KeyPairIds': [self.lease['key_pair_id']]}, 'InvalidKeyPairID.NotFound'),
            ('iam', 'get-role', {'RoleName': self.session.name}, 'NoSuchEntity'),
        ]
        for service, action, payload, missing in actions:
            try:
                value = self.aws.call(service, action, payload)
                if service == 'scheduler':
                    expected = schedule_request(self.session)
                    if (value['Target']['RoleArn'] != self.session.role_arn
                            or json.loads(value['Target']['Input']) != json.loads(expected['Target']['Input'])):
                        raise ValueError('Foreign schedule cannot be deleted')
                    self.aws.call(service, 'delete-schedule', payload)
                elif action == 'describe-security-groups':
                    record = value['SecurityGroups'][0]
                    self.session.check_tags(record.get('Tags', []))
                    if record['GroupName'] != self.session.name:
                        raise ValueError('Foreign security group cannot be deleted')
                    self.aws.call(service, 'delete-security-group', {'GroupId': self.lease['security_group_id']})
                elif action == 'describe-key-pairs':
                    record = value['KeyPairs'][0]
                    self.session.check_tags(record.get('Tags', []))
                    if record['KeyName'] != self.session.name:
                        raise ValueError('Foreign key pair cannot be deleted')
                    self.aws.call(service, 'delete-key-pair', {'KeyPairId': self.lease['key_pair_id']})
                else:
                    role = value['Role']
                    self.session.check_tags(role.get('Tags', []))
                    if role['Arn'] != self.session.role_arn:
                        raise ValueError('Foreign IAM role cannot be deleted')
                    try:
                        self.aws.call('iam', 'delete-role-policy', {'RoleName': self.session.name, 'PolicyName': 'terminate-fixture'})
                    except AwsError as error:
                        if error.code != 'NoSuchEntity':
                            raise
                    self.aws.call('iam', 'delete-role', {'RoleName': self.session.name})
            except AwsError as error:
                if error.code != missing:
                    pending.append(str(error))
            except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as error:
                pending.append(str(error))
        try:
            self.remove_private_key()
        except (ValueError, OSError) as error:
            pending.append(str(error))
        self.result['cleanup_complete'] = not pending
        self.event('cleanup_finished', pending=pending)
        if pending:
            raise RuntimeError('Fixture cleanup incomplete; see receipt')

    def remove_private_key(self) -> None:
        config = self.lease.get('ssh')
        if not config:
            return
        path = Path(config['key'])
        resolved = path.resolve()
        if (path.is_symlink() or not resolved.is_relative_to(self.receipt.parent.resolve())
                or resolved.parent.name != self.session.name or resolved.name != 'fixture_ed25519'):
            raise ValueError('Private key path is outside this fixture receipt directory')
        if path.exists():
            if hashlib.sha256(path.read_bytes()).hexdigest() != config['key_sha256']:
                raise ValueError('Private key content changed; preserving the file')
            path.unlink()
            self.event('local_private_key_removed')

    def supervise(self, command: list[str]) -> int:
        process = None
        failure = None
        try:
            if any(event['phase'] == 'workload_started' for event in self.result['events']):
                raise ValueError('Workload was already started; resume cleanup without replaying it')
            self.check_ready()
            limit = min(self.session.remaining(51), self.monotonic_end - time.monotonic() - 9 * 60)
            if limit <= 0:
                raise TimeoutError('No workload time remains')
            with self.receipt.with_suffix('.workload.log').open('wb') as log:
                process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                    start_new_session=os.name != 'nt',
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0)
                self.event('workload_started', pid=process.pid)
                try:
                    code = process.wait(timeout=limit)
                except subprocess.TimeoutExpired as error:
                    raise TimeoutError('Absolute fixture workload deadline exceeded') from error
                self.event('workload_finished', exit=code)
                return code
        except (ValueError, RuntimeError, OSError, subprocess.SubprocessError, KeyboardInterrupt) as error:
            failure = error
            self.event('workload_failed', error_type=type(error).__name__, error=str(error))
            raise
        finally:
            try:
                if process and process.poll() is None:
                    if os.name == 'nt':
                        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                                       capture_output=True, timeout=10, check=True)
                    else:
                        os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=10)
                    self.event('local_process_stopped')
            finally:
                try:
                    self.cleanup()
                except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as error:
                    self.event('cleanup_failed', error_type=type(error).__name__, error=str(error))
                    if failure is not None:
                        failure.add_note('Cleanup also failed: ' + str(error))
                        raise failure from error
                    raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('render', 'check', 'supervise', 'cleanup'))
    parser.add_argument('--lease', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--allow-cloud-cleanup', action='store_true')
    parser.add_argument('--command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    lease = json.loads(args.lease.read_text())
    session = Session.read(lease)
    if args.action == 'render':
        args.output.mkdir(parents=True, exist_ok=True)
        write_json(args.output / 'schedule.json', schedule_request(session))
        write_json(args.output / 'termination-policy.json', termination_policy(session))
        write_json(args.output / 'trust-policy.json', trust_policy(session))
        for name, content in watchdog_units(session).items():
            (args.output / name).write_text(content, encoding='utf-8', newline='\n')
        print('NATIVE_WATCHDOG_INPUTS_RENDERED_OFFLINE')
        return
    if args.action in ('cleanup', 'supervise') and not args.allow_cloud_cleanup:
        parser.error('Cloud mutation requires --allow-cloud-cleanup')
    if args.action == 'supervise' and not args.command:
        parser.error('Supervision requires --command')
    controller = Controller(lease, AwsCli(session.region), args.output)
    if args.action == 'check':
        controller.check_ready()
    elif args.action == 'cleanup':
        controller.cleanup()
    else:
        def interrupted(signum, frame):
            raise KeyboardInterrupt('Fixture controller interrupted')
        signal.signal(signal.SIGTERM, interrupted)
        raise SystemExit(controller.supervise(args.command))


if __name__ == '__main__':
    main()
