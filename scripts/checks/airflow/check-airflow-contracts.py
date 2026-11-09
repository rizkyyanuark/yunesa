"""Verify trusted release inputs and lifecycle failure boundaries on Linux."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from airflow_operations import AIRFLOW_SECRETS, IMAGE_KINDS, TRUSTED_FILES, AirflowOperations  # noqa: E402
from airflow_operations import (  # noqa: E402
    configuration_digest, deployment_architecture, deployment_endpoints, deployment_project, lifecycle_lock,
    deployment_airflow_log_volume,
)
from yunesa_airflow.admission import atomic_json, require_open, set_gate  # noqa: E402

spec = importlib.util.spec_from_file_location('deployment', Path(__file__).resolve().parents[2] / 'deploy-production.py')
deployment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deployment)


class ReleaseTests(unittest.TestCase):
    def test_persistent_log_volume_selection(self):
        self.assertEqual(deployment_airflow_log_volume({}), 'yunesa-app_airflow-logs')
        current = {'YUNESA_AIRFLOW_LOG_VOLUME': 'legacy_airflow-logs'}
        self.assertEqual(deployment_airflow_log_volume({}, current), 'legacy_airflow-logs')
        self.assertEqual(deployment_airflow_log_volume({'airflow_log_volume': 'legacy_airflow-logs'}, current),
                         'legacy_airflow-logs')
        for name in ('', '/host/path', '../logs', 'invalid name', 'x' * 256):
            with self.subTest(name=name), self.assertRaises(ValueError):
                deployment_airflow_log_volume({'airflow_log_volume': name})
        with self.assertRaises(ValueError):
            deployment_airflow_log_volume({'airflow_log_volume': 'different-logs'}, current)

    def setUp(self):
        self.registry = {'registry': 'registry.test:443', 'image_prefix': 'registry.test:443/owner/yunesa',
                         'config_sha256': 'configuration'}
        self.payload = {'CI_COMMIT_SHA': 'a' * 40, 'CI_REGISTRY': self.registry['registry'],
                        'CI_REGISTRY_IMAGE': self.registry['image_prefix'], 'CI_REGISTRY_USER': 'job',
                        'CI_REGISTRY_PASSWORD': 'fixture', 'YUNESA_CONFIG_SHA256': 'configuration',
                        'GLOBAL_PASSWORD': 'integration_only_password', 'JWT_SECRET_KEY': 'fixture',
                        'GEMINI_API_KEY': 'unavailable', 'SILICONFLOW_API_KEY': 'unavailable',
                        'ADMIN_PASSWORD': 'fixture', **{name: 'fixture' for name in AIRFLOW_SECRETS}}
        for kind in IMAGE_KINDS:
            self.payload[f'YUNESA_{kind}_IMAGE'] = (
                self.registry['image_prefix'] + '/' + kind.lower().replace('_', '-') + '@sha256:' + 'b' * 64)

    def test_all_digest_inputs(self):
        deployment.validate_request(self.payload, 'deploy', self.registry)

    def test_trusted_readiness_endpoints(self):
        self.assertEqual(deployment_endpoints({})['public_base_url'], 'https://yunesa.tugasakhir.space')
        endpoints = deployment_endpoints({'public_base_url': 'http://web/', 'local_base_url': 'http://web'})
        self.assertEqual(endpoints, {'public_base_url': 'http://web', 'local_base_url': 'http://web'})
        for value in ('file:///etc/passwd', 'http://user:password@web', 'http://web?key=secret',
                      'http://web/#fragment', 'http://web:invalid', 'http://web:0', 'http://web\n', None):
            with self.subTest(value=value), self.assertRaises(deployment.DeployError):
                deployment.validate_request(self.payload, 'deploy', {**self.registry, 'public_base_url': value})

    def test_trusted_compose_namespace(self):
        self.assertEqual(deployment_project({}), 'yunesa-app')
        self.assertEqual(deployment_project({'project': 'yunesa-airflow-it-d81c590f'}), 'yunesa-airflow-it-d81c590f')
        for value in ('../production', 'Yunesa', '-invalid', '', None, 'a' * 64):
            with self.subTest(value=value), self.assertRaises(deployment.DeployError):
                deployment.validate_request(self.payload, 'deploy', {**self.registry, 'project': value})

    def test_deployment_deadline_configuration(self):
        name = 'YUNESA_AIRFLOW_READINESS_DEADLINE'
        previous = os.environ.pop(name, None)
        try:
            self.assertEqual(deployment.airflow_deadline(name, 180), 180)
            os.environ[name] = '600'
            self.assertEqual(deployment.airflow_deadline(name, 180), 600)
            for value in ('0', '-1', '3601', 'invalid'):
                os.environ[name] = value
                with self.subTest(value=value), self.assertRaises(deployment.DeployError):
                    deployment.airflow_deadline(name, 180)
        finally:
            os.environ.pop(name, None)
            if previous is not None:
                os.environ[name] = previous

    def test_root_installed_architecture(self):
        self.assertEqual(deployment_architecture({}), 'arm64')
        self.assertEqual(deployment_architecture({'architecture': 'amd64'}), 'amd64')
        for value in ('x86_64', 'windows/amd64', '', None, ['arm64']):
            with self.subTest(value=value), self.assertRaises(deployment.DeployError):
                deployment.validate_request(self.payload, 'deploy', {**self.registry, 'architecture': value})

    def test_mutable_and_foreign_images_rejected(self):
        for image in ('registry.test:443/owner/yunesa/etl-worker:latest',
                      'foreign.test/etl-worker@sha256:' + 'b' * 64):
            with self.subTest(image=image), self.assertRaises(deployment.DeployError):
                deployment.validate_request({**self.payload, 'YUNESA_ETL_WORKER_IMAGE': image}, 'deploy', self.registry)

    def test_unknown_fields_and_checksum_drift_rejected(self):
        for change in ({'SHELL': 'arbitrary'}, {'YUNESA_CONFIG_SHA256': 'different'},
                       {'YUNESA_AIRFLOW_LOG_VOLUME': 'untrusted-logs'}, {'airflow_log_volume': 'untrusted-logs'},
                       {'project': 'other-project'}, {'local_base_url': 'http://other-host'},
                       {'public_base_url': 'http://other-host'}, {'architecture': 'amd64'}):
            with self.subTest(change=change), self.assertRaises(deployment.DeployError):
                deployment.validate_request({**self.payload, **change}, 'deploy', self.registry)

    def test_source_installed_checksum_and_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for source, destination in TRUSTED_FILES.items():
                for relative in (source, 'installed/' + destination):
                    path = root / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(source)
            self.assertEqual(configuration_digest(root), configuration_digest(root / 'installed', installed=True))
            (root / 'scripts/airflow_operations.py').write_text('changed')
            self.assertNotEqual(configuration_digest(root), configuration_digest(root / 'installed', installed=True))


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.release = self.root / 'releases/a'
        self.release.mkdir(parents=True)
        atomic_json(self.release / 'manifest.json', {
            'project': 'yunesa-airflow-it-contract', 'airflow_version': '3.1.7',
            'airflow_image': 'airflow:fixture', 'etl_worker_image': 'worker:fixture'}, mode=0o600)
        (self.release / '.env').write_text("YUNESA_AIRFLOW_IMAGE='airflow:fixture'\nYUNESA_ETL_WORKER_IMAGE='worker:fixture'\n")
        (self.release / '.env').chmod(0o600)
        (self.root / 'current').symlink_to(self.release)
        self.operation = AirflowOperations(self.root)
        self.executable = str(Path(__file__).resolve().parents[2] / 'airflow_operations.py')

    def tearDown(self):
        self.temporary.cleanup()

    def test_fresh_off_and_missing_admission(self):
        self.assertEqual(self.operation.state(), {'requested': 'off', 'phase': 'off'})
        with self.assertRaises(RuntimeError):
            require_open(self.operation.control, self.release.name)

    def test_invalid_arguments(self):
        for arguments in (['unsupported'], ['off', '--deadline', '0'], ['off', '--deadline', '3601']):
            result = subprocess.run([sys.executable, self.executable, *arguments], capture_output=True)
            self.assertEqual(result.returncode, 2)
        self.assertFalse(self.operation.state_path.exists())

    def test_unauthorized_user(self):
        result = subprocess.run([sys.executable, self.executable, 'off'], capture_output=True, text=True,
                                preexec_fn=lambda: os.setuid(65534))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('authorized administrative SSH', result.stderr)

    def test_busy_does_not_mutate_state(self):
        with lifecycle_lock(self.root):
            result = subprocess.run([sys.executable, self.executable, 'off', '--root', str(self.root)],
                                    capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Lifecycle busy', result.stderr)
        self.assertFalse(self.operation.state_path.exists())

    def test_closed_release_and_boot_gate(self):
        self.operation.save({'requested': 'off', 'phase': 'off'})
        control = self.operation.control
        set_gate(control, False, self.release.name)
        with self.assertRaises(RuntimeError):
            require_open(control, self.release.name)
        set_gate(control, True, self.release.name)
        require_open(control, self.release.name)
        with self.assertRaises(RuntimeError):
            require_open(control, 'different-release')
        gate = json.loads((control / 'gate.json').read_text())
        atomic_json(control / 'gate.json', {**gate, 'boot_id': 'previous-boot'})
        with self.assertRaises(RuntimeError):
            require_open(control, self.release.name)

    def test_image_mismatch_closes_direct_on_before_docker(self):
        self.operation.save({'requested': 'on', 'phase': 'on'})
        set_gate(self.operation.control, True, self.release.name)
        (self.release / '.env').write_text("YUNESA_AIRFLOW_IMAGE='wrong:fixture'\nYUNESA_ETL_WORKER_IMAGE='worker:fixture'\n")
        with self.assertRaisesRegex(RuntimeError, 'image identities do not match'):
            self.operation.on()
        with self.assertRaises(RuntimeError):
            require_open(self.operation.control, self.release.name)

    def test_corrupt_state_fail_closed(self):
        self.operation.save({'requested': 'on', 'phase': 'starting'})
        for corrupted in ('{broken', '{"requested":"invalid","phase":"off"}'):
            self.operation.state_path.write_text(corrupted)
            set_gate(self.operation.control, True, self.release.name)
            with self.assertRaises((RuntimeError, ValueError)):
                self.operation.transition_state()
            with self.assertRaises(RuntimeError):
                require_open(self.operation.control, self.release.name)


if __name__ == '__main__':
    unittest.main()
