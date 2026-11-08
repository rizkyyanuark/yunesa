from __future__ import annotations

import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


def boot_id() -> str:
    return Path('/proc/sys/kernel/random/boot_id').read_text().strip()


def atomic_json(path: Path, value: dict, mode: int = 0o660) -> None:
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, 'w') as stream:
            json.dump(value, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


@contextmanager
def launch_lock(directory: Path) -> Iterator[None]:
    with (directory / 'launch.lock').open('a+') as stream:
        if os.fstat(stream.fileno()).st_uid == os.geteuid():
            os.fchmod(stream.fileno(), 0o660)
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def set_gate(directory: Path, opened: bool, release: str) -> None:
    with launch_lock(directory):
        atomic_json(directory / 'gate.json', {'open': opened, 'boot_id': boot_id(), 'release': release})


def require_open(directory: Path, release: str) -> None:
    try:
        gate = json.loads((directory / 'gate.json').read_text())
    except (OSError, ValueError) as error:
        raise RuntimeError('ETL admission unavailable; run the managed on operation') from error
    if gate.get('open') is not True or gate.get('boot_id') != boot_id() or gate.get('release') != release:
        raise RuntimeError('ETL admission closed or release/boot reconciliation required')
