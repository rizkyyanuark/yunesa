"""Exercise image platform and worker observation against a local Docker daemon."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from airflow_operations import AirflowOperations  # noqa: E402
from yunesa_airflow.admission import atomic_json  # noqa: E402

spec = importlib.util.spec_from_file_location('deployment', Path(__file__).resolve().parents[2] / 'deploy-production.py')
deployment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deployment)


class DockerContracts(unittest.TestCase):
    def setUp(self):
        self.image = os.environ.get('YUNESA_CONTRACT_IMAGE', 'yunesa-airflow-check:local')

    def test_real_image_architecture_guard(self):
        inspected = json.loads(subprocess.check_output(['docker', 'image', 'inspect', self.image]))[0]
        actual = inspected['Architecture']
        self.assertIn(actual, ('amd64', 'arm64'))
        previous = deployment.ARCHITECTURE
        try:
            deployment.ARCHITECTURE = 'arm64' if actual == 'amd64' else 'amd64'
            with self.assertRaises(deployment.DeployError):
                deployment.image_platform(self.image)
            deployment.ARCHITECTURE = actual
            deployment.image_platform(self.image)
        finally:
            deployment.ARCHITECTURE = previous

    def test_workers_disappearing_during_observation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            release = root / 'releases/a'
            release.mkdir(parents=True)
            atomic_json(release / 'manifest.json', {'project': 'yunesa-airflow-it-contract'}, mode=0o600)
            project = 'yunesa-airflow-observe-' + os.urandom(4).hex()
            operation = AirflowOperations(root, release, project=project)
            label = 'io.yunesa.etl.project=' + project
            try:
                for _ in range(3):
                    subprocess.run(['docker', 'run', '--rm', '-d', '--network', 'none', '--memory', '32m',
                                    '--memory-swap', '64m', '--label', label, '--entrypoint', 'python',
                                    self.image, '-c', 'import time; time.sleep(2)'],
                                   check=True, capture_output=True, timeout=30)
                deadline = time.monotonic() + 30
                while operation.workers(include_exited=True) and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertEqual(operation.workers(include_exited=True), [])
            finally:
                remaining = subprocess.run(['docker', 'ps', '-aq', '--filter', 'label=' + label],
                                           check=True, capture_output=True, text=True, timeout=30)
                for identifier in remaining.stdout.split():
                    subprocess.run(['docker', 'rm', '-f', identifier], check=True, capture_output=True, timeout=30)


if __name__ == '__main__':
    unittest.main()
