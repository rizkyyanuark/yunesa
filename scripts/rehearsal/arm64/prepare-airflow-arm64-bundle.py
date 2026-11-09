"""Export verified local ARM64 images and the capacity runner without publication."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import shutil
import subprocess
import tarfile
import time
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[3]
API_IMAGE = 'yunesa-api:capacity-native-arm64'
IMAGES = [API_IMAGE, *['yunesa-' + name + ':integration-arm64'
          for name in ('web', 'minio', 'airflow', 'etl-worker')],
          *['yunesa-arm64-proof/' + name + ':local' for name in ('postgres', 'redis', 'graph', 'vector')]]
SOURCE_PATHS = ['docker-compose.prod.yml', 'orchestration', 'scripts/airflow_operations.py',
    'scripts/rehearsal/arm64/airflow_capacity_session.py', 'scripts/yunesa-airflow.sh',
    'scripts/rehearsal/arm64/airflow-native-controller.py',
    'scripts/rehearsal/arm64/check-airflow-arm64-vm.py',
    'scripts/rehearsal/arm64/check-airflow-arm64-capacity.py', 'scripts/checks/airflow/check-airflow-core-release.py',
    'scripts/checks/airflow/check-airflow-kernel-guest.py', 'scripts/airflow-local-check.py',
    'scripts/deployment-readiness.py', 'backend/server/worker_health.py']


def run(*args: str, timeout: int = 600) -> bytes:
    result = subprocess.run(args, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f'{args[:3]} failed ({result.returncode}): ' + result.stderr.decode(errors='replace')[-1000:])
    return result.stdout


def sha256(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def image_files(image: str, pairs: dict[str, str]) -> dict[str, str]:
    identifier = run('docker', 'create', '--platform', 'linux/arm64',
                     '--label', 'io.yunesa.capacity.bundle=local', image).decode().strip()
    result = {}
    try:
        for local, remote in pairs.items():
            archive = run('docker', 'cp', identifier + ':' + remote, '-')
            with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
                member = next(item for item in stream.getmembers() if item.isfile())
                content = stream.extractfile(member).read()
            expected = (SOURCE / local).read_bytes()
            if content != expected:
                raise ValueError(f'{image} embeds a different source file: {local}')
            result[local] = hashlib.sha256(content).hexdigest()
    finally:
        run('docker', 'rm', identifier)
    return result


def embedded_source() -> dict:
    result = {API_IMAGE: image_files(API_IMAGE,
        {'backend/server/worker_health.py': '/app/server/worker_health.py'})}
    paths = [path for path in (SOURCE / 'orchestration').rglob('*.py') if '__pycache__' not in path.parts]
    result['airflow'] = image_files('yunesa-airflow:integration-arm64',
        {path.relative_to(SOURCE).as_posix(): '/opt/airflow/' + path.relative_to(SOURCE / 'orchestration').as_posix()
         for path in paths})
    worker_paths = ['backend/package/yunesa/etl/run_worker.py',
        'backend/package/yunesa/etl/pipelines/kg_construction.py',
        'backend/package/yunesa/etl/services/kg_service.py',
        'backend/package/yunesa/knowledge/__init__.py',
        'backend/package/yunesa/knowledge/services/kg_storage_service.py',
        'backend/package/yunesa/knowledge/graphs/storage_neo4j.py']
    result['etl-worker'] = image_files('yunesa-etl-worker:integration-arm64',
        {name: '/app/package/' + name.removeprefix('backend/package/') for name in worker_paths})
    return result


def verify_archive(path: Path) -> dict:
    configs = {}
    manifest = None
    with gzip.open(path, 'rb') as compressed:
        with tarfile.open(fileobj=compressed, mode='r|') as archive:
            for item in archive:
                if item.isfile() and item.size <= 8 * 1024**2:
                    if item.name == 'manifest.json':
                        manifest = json.load(archive.extractfile(item))
                    elif item.name.endswith('.json') or item.name.startswith('blobs/sha256/'):
                        content = archive.extractfile(item).read()
                        try:
                            value = json.loads(content)
                        except (ValueError, UnicodeError):
                            continue
                        if isinstance(value, dict) and 'architecture' in value:
                            configs[item.name] = value
        while compressed.read(1024**2):
            pass
    if not manifest:
        raise ValueError('Image archive has no Docker manifest')
    tags = set()
    for entry in manifest:
        config = configs[entry['Config']]
        if config['architecture'] != 'arm64' or config['os'] != 'linux':
            raise ValueError('Image archive contains a non-ARM64 Linux configuration')
        tags.update(entry.get('RepoTags') or [])
    if tags != set(IMAGES):
        raise ValueError(f'Archive tag set differs from bundle inputs: {tags}')
    return {'images': len(manifest), 'platform': 'linux/arm64', 'tags': sorted(tags), 'gzip_crc': 'passed'}


def source_archive(output: Path) -> dict[str, str]:
    source_hashes = {}
    with tarfile.open(output / 'source.tar.gz', 'w:gz') as stream:
        for name in SOURCE_PATHS:
            path = SOURCE / name
            paths = sorted(path.rglob('*')) if path.is_dir() else [path]
            for item in paths:
                if path.is_dir() and item.suffix != '.py':
                    continue
                if item.is_file() and '__pycache__' not in item.parts and item.suffix != '.pyc':
                    relative = item.relative_to(SOURCE).as_posix()
                    stream.add(item, arcname=relative)
                    source_hashes[relative] = sha256(item)
    return source_hashes


def prepare(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    if (output / 'bundle.json').exists():
        raise ValueError('Bundle already exists; verify it or use a new output directory')
    context = output / 'api-context'
    context.mkdir(exist_ok=True)
    parent = json.loads(run('docker', 'image', 'inspect', '--platform=linux/arm64', 'yunesa-api:integration-arm64'))[0]
    if parent['Architecture'] != 'arm64':
        raise ValueError('API base must already be ARM64')
    shutil.copyfile(SOURCE / 'backend/server/worker_health.py', context / 'worker_health.py')
    (context / 'Dockerfile').write_text(
        'FROM yunesa-api:integration-arm64\nCOPY worker_health.py /app/server/worker_health.py\n')
    run('docker', 'build', '--platform', 'linux/arm64', '--tag', API_IMAGE, str(context), timeout=1200)
    images = json.loads(run('docker', 'image', 'inspect', '--platform=linux/arm64', *IMAGES))
    if any(item['Architecture'] != 'arm64' or item['Os'] != 'linux' for item in images):
        raise ValueError('Every bundle image must be Linux ARM64')
    embedded = embedded_source()
    archive = output / 'images.tar.gz'
    temporary = output / 'images.tar.gz.partial'
    started = time.monotonic()
    with (output / 'docker-save.stderr').open('wb') as errors:
        process = subprocess.Popen(['docker', 'image', 'save', '--platform=linux/arm64', *IMAGES],
                                   stdout=subprocess.PIPE, stderr=errors)
        try:
            with temporary.open('wb') as target, gzip.GzipFile(fileobj=target, mode='wb', compresslevel=1, mtime=0) as zipped:
                shutil.copyfileobj(process.stdout, zipped, length=1024**2)
            if process.wait(timeout=120) != 0:
                raise RuntimeError('Docker image export failed; inspect docker-save.stderr')
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
    temporary.replace(archive)
    verified = verify_archive(archive)
    source_hashes = source_archive(output)
    manifest = {'schema': 1, 'platform': 'linux/arm64', 'images': [
        {'ref': ref, 'id': item['Id'], 'size': item['Size']} for ref, item in zip(IMAGES, images, strict=True)],
        'embedded_source': embedded, 'source_files': source_hashes,
        'git_head': run('git', '-C', str(SOURCE), 'rev-parse', 'HEAD').decode().strip(),
        'working_tree': 'uncommitted source manifest is authoritative', 'archive_verification': verified,
        'artifacts': {path.name: {'bytes': path.stat().st_size, 'sha256': sha256(path)}
                      for path in (archive, output / 'source.tar.gz')},
        'elapsed_seconds': time.monotonic() - started}
    (output / 'bundle.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest['artifacts'], indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('prepare', 'verify', 'refresh-source'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    cache = (SOURCE / '.cache').resolve()
    if not output.is_relative_to(cache):
        parser.error('Bundle output must remain inside repository .cache')
    if args.action == 'prepare':
        prepare(output)
    else:
        manifest = json.loads((output / 'bundle.json').read_text())
        artifacts = manifest['artifacts']
        if args.action == 'refresh-source':
            artifacts = {'images.tar.gz': artifacts['images.tar.gz']}
        for name, expected in artifacts.items():
            if name not in ('images.tar.gz', 'source.tar.gz'):
                raise ValueError('Unexpected bundle artifact')
            if sha256(output / name) != expected['sha256'] or (output / name).stat().st_size != expected['bytes']:
                raise ValueError('Bundle artifact checksum or size mismatch')
        verify_archive(output / 'images.tar.gz')
        for records in manifest['embedded_source'].values():
            for name, expected in records.items():
                if sha256(SOURCE / name) != expected:
                    raise ValueError('Embedded application source changed; rebuild its image before bundling')
        if args.action == 'refresh-source':
            manifest['embedded_source'] = embedded_source()
            manifest['source_files'] = source_archive(output)
            source = output / 'source.tar.gz'
            manifest['artifacts'][source.name] = {'bytes': source.stat().st_size, 'sha256': sha256(source)}
            (output / 'bundle.json').write_text(json.dumps(manifest, indent=2))
        for name, expected in manifest['source_files'].items():
            path = (SOURCE / name).resolve()
            if not path.is_relative_to(SOURCE) or sha256(path) != expected:
                raise ValueError('Bundled source changed; prepare a new bundle')
        print('ARM64_BUNDLE_VERIFIED')


if __name__ == '__main__':
    main()
