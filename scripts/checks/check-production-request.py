"""Check release identity, stale pipelines and the privileged wrapper boundary."""

from __future__ import annotations

import copy
import importlib.util
import io
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SOURCE / 'scripts'))
from airflow_operations import AIRFLOW_SECRETS, IMAGE_KINDS, TRUSTED_FILES, configuration_digest  # noqa: E402

spec = importlib.util.spec_from_file_location('request', SOURCE / 'scripts/production-request.py')
request = importlib.util.module_from_spec(spec)
spec.loader.exec_module(request)

deployment_spec = importlib.util.spec_from_file_location('deployment', SOURCE / 'scripts/deploy-production.py')
deployment = importlib.util.module_from_spec(deployment_spec)
deployment_spec.loader.exec_module(deployment)


class RequestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repository = tempfile.TemporaryDirectory()
        cls.origin = Path(cls.repository.name) / 'origin.git'
        subprocess.run(['git', 'init', '--bare', '-q', str(cls.origin)], check=True)
        tree = subprocess.check_output(['git', '--git-dir', str(cls.origin), 'hash-object', '-t', 'tree',
                                        '-w', '--stdin'], input=b'').decode().strip()
        cls.revision = subprocess.check_output(
            ['git', '--git-dir', str(cls.origin), '-c', 'user.name=Release fixture',
             '-c', 'user.email=fixture@localhost', 'commit-tree', tree], input=b'Isolated fixture\n').decode().strip()
        subprocess.run(['git', '--git-dir', str(cls.origin), 'update-ref', 'refs/heads/main', cls.revision], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.repository.cleanup()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.previous = Path.cwd()
        os.chdir(self.directory)
        subprocess.run(['git', 'init', '-q'], check=True)
        subprocess.run(['git', 'remote', 'add', 'origin', str(self.origin)], check=True)
        self.environment = {
            'CI_COMMIT_SHA': self.revision, 'CI_DEFAULT_BRANCH': 'main', 'CI_COMMIT_BRANCH': 'main',
            'CI_COMMIT_REF_PROTECTED': 'true', 'CI_REGISTRY': 'registry.test',
            'CI_REGISTRY_IMAGE': 'registry.test/owner/yunesa', 'CI_REGISTRY_USER': 'job',
            'CI_REGISTRY_PASSWORD': 'private-registry-fixture',
            **{name: 'private-secret-fixture' for name in (*AIRFLOW_SECRETS, 'GLOBAL_PASSWORD',
               'JWT_SECRET_KEY', 'GEMINI_API_KEY', 'SILICONFLOW_API_KEY', 'ADMIN_PASSWORD')},
        }
        for kind in IMAGE_KINDS:
            self.environment['YUNESA_' + kind + '_IMAGE'] = (
                self.environment['CI_REGISTRY_IMAGE'] + '/' + kind.lower().replace('_', '-') + '@sha256:' + 'b' * 64)
        self.payload = {**self.environment, 'YUNESA_CONFIG_SHA256': configuration_digest(SOURCE)}
        self.proof = {
            'operation': 'deploy', 'status': 'passed', 'release': self.revision + '-20261110000000',
            'project': 'yunesa-app', 'commit': self.revision, 'config_sha256': self.payload['YUNESA_CONFIG_SHA256'],
            'images': {kind: self.environment['YUNESA_' + kind + '_IMAGE'] for kind in IMAGE_KINDS},
            'airflow': {'requested': 'off', 'phase': 'off'},
            'readiness': {
                'storage': dict.fromkeys(('postgres', 'redis_write_read', 'memgraph_query', 'qdrant',
                                          'minio_upload_download_delete', 'public_object_bytes',
                                          'private_bucket_proxy_denied', 'public_bucket_listing_denied'), 'passed'),
                'http_local': dict.fromkeys(('frontend', 'login', 'authorization', 'conversation_write_read_delete',
                                             'async_chat', 'assistant_response_persisted'), 'passed'),
                'http_public': dict.fromkeys(('frontend', 'login', 'authorization',
                                              'conversation_write_read_delete'), 'passed'),
                'providers': {'chat': 'passed', 'embedding': 'passed'},
            },
        }
        self.wrapper_calls = []

    def tearDown(self):
        os.chdir(self.previous)
        self.temporary.cleanup()

    def invoke(self, *, output: bytes | None = None, exit_code: int = 0, protocol: int = 2,
               stderr: bytes = b'private-secret-fixture') -> int:
        run = subprocess.run

        def boundary(arguments, **kwargs):
            if arguments[0] != 'sudo':
                return run(arguments, **kwargs)
            if kwargs.get('input') == b'{"release_evidence_protocol":2}':
                self.wrapper_calls.append('protocol')
                return subprocess.CompletedProcess(arguments, 0, json.dumps({'release_evidence_protocol': protocol,
                                                    'operation_seconds': 1800, 'recovery_seconds': 1200}).encode(), b'')
            self.wrapper_calls.append(arguments[-1])
            self.assertEqual(kwargs['timeout'], 3120)
            return subprocess.CompletedProcess(arguments, exit_code,
                                               output if output is not None else json.dumps(self.proof).encode(),
                                               stderr)

        with patch.dict(os.environ, self.environment), patch.object(sys, 'argv', ['production-request.py', 'deploy']), \
                patch.object(request.subprocess, 'run', side_effect=boundary):
            return request.main()

    def test_real_git_latest_head(self):
        request.require_latest_commit(self.environment)

    def test_stale_pipeline_stops_before_wrapper(self):
        self.environment['CI_COMMIT_SHA'] = 'a' * 40
        self.assertEqual(self.invoke(), 1)
        self.assertEqual(self.wrapper_calls, [])
        self.assertEqual(json.loads(Path('artifacts/production-release.json').read_text())['stage'], 'freshness')

    def test_unprotected_or_nondefault_branch_rejected(self):
        for values in ({'CI_COMMIT_REF_PROTECTED': 'false'}, {'CI_COMMIT_BRANCH': 'feature'}, {'CI_COMMIT_SHA': 'short'}):
            with self.subTest(values=values), self.assertRaises(request.RequestError):
                request.require_latest_commit({**self.environment, **values})

    def test_unavailable_remote_fails_closed(self):
        subprocess.run(['git', 'remote', 'set-url', 'origin', str(self.directory / 'missing.git')], check=True)
        self.assertEqual(self.invoke(), 1)
        self.assertEqual(self.wrapper_calls, [])

    def test_old_wrapper_stops_before_deployment(self):
        self.assertEqual(self.invoke(protocol=0), 1)
        self.assertEqual(self.wrapper_calls, ['protocol'])

    def test_verified_artifacts_remove_unknown_fields_and_credentials(self):
        self.proof['secret'] = 'private-secret-fixture'
        self.proof['readiness']['storage']['secret'] = 'private-secret-fixture'
        self.proof['airflow']['secret'] = 'private-secret-fixture'
        self.assertEqual(self.invoke(), 0)
        release = json.loads(Path('artifacts/production-release.json').read_text())
        health = json.loads(Path('artifacts/production-health.json').read_text())
        self.assertEqual(release['commit'], self.revision)
        self.assertEqual(release['images'], self.proof['images'])
        self.assertEqual(health['status'], 'passed')
        for path in Path('artifacts').glob('*.json'):
            self.assertNotIn('private-secret-fixture', path.read_text())

    def test_failed_wrapper_records_recovery_without_raw_output(self):
        output = b'{"operation":"automatic_rollback","status":"passed"}\nprivate-secret-fixture'
        self.assertEqual(self.invoke(output=output, exit_code=1), 1)
        report = json.loads(Path('artifacts/production-release.json').read_text())
        self.assertEqual(report['automatic_rollback'], 'passed')
        self.assertEqual(report['wrapper_exit_code'], 1)
        self.assertNotIn('private-secret-fixture', Path('artifacts/production-release.json').read_text())

    def test_safe_failure_reference_reaches_artifact(self):
        failure = {'status': 'failed', 'stage': 'verification', 'category': 'deadline',
                   'recovery_status': 'passed', 'diagnostic_reference': 'release-' + 'c' * 32,
                   'message': 'private-secret-fixture'}
        self.assertEqual(self.invoke(exit_code=1, stderr=json.dumps(failure).encode()), 1)
        report = json.loads(Path('artifacts/production-release.json').read_text())
        self.assertEqual(report['diagnostic_reference'], failure['diagnostic_reference'])
        self.assertEqual(report['stage'], 'verification')
        self.assertEqual(report['recovery_status'], 'passed')
        self.assertNotIn('private-secret-fixture', Path('artifacts/production-release.json').read_text())

    def test_untrusted_failure_fields_are_not_published(self):
        base = {'status': 'failed', 'stage': 'verification', 'category': 'deadline',
                'recovery_status': 'passed', 'diagnostic_reference': 'release-' + 'c' * 32}
        for fields in ({'stage': ['private-secret-fixture']}, {'category': 'private-secret-fixture'},
                       {'diagnostic_reference': '../../private-secret-fixture'}, {'recovery_status': None}):
            with self.subTest(fields=fields):
                self.assertEqual(request.wrapper_failure(json.dumps({**base, **fields}).encode()), {})

    def test_protocol_budget_reserves_recovery_and_ci_headroom(self):
        policy = {'release_evidence_protocol': 2, 'operation_seconds': 1800, 'recovery_seconds': 1200}
        self.assertEqual(request.wrapper_timeout(policy), 3120)
        for fields in ({'release_evidence_protocol': 1}, {'operation_seconds': True},
                       {'recovery_seconds': 0}, {'operation_seconds': 3600}):
            with self.subTest(fields=fields), self.assertRaises(request.RequestError):
                request.wrapper_timeout({**policy, **fields})

    def test_invalid_json_or_incomplete_receipt_is_failure(self):
        for output in (b'not json', b'{}'):
            with self.subTest(output=output):
                self.assertEqual(self.invoke(output=output), 1)
                self.assertEqual(json.loads(Path('artifacts/production-health.json').read_text())['status'], 'unconfirmed')

    def test_each_image_mismatch_rejected(self):
        for kind in IMAGE_KINDS:
            changed = copy.deepcopy(self.proof)
            changed['images'][kind] = changed['images'][kind].replace('b' * 64, 'c' * 64)
            with self.subTest(kind=kind), self.assertRaises(request.RequestError):
                request.verify_release(changed, self.payload, 'deploy')

    def test_identity_readiness_and_lifecycle_failures(self):
        mutations = [({'commit': 'a' * 40}), ({'config_sha256': 'c' * 64}), ({'operation': 'rollback'}),
                     ({'airflow': {'requested': 'on', 'phase': 'starting'}}),
                     ({'readiness': {'storage': {'postgres': 'passed'}}})]
        for fields in mutations:
            with self.subTest(fields=fields), self.assertRaises(request.RequestError):
                request.verify_release({**self.proof, **fields}, self.payload, 'deploy')

    def test_rollback_receipt_uses_target_identity_and_supports_legacy_off(self):
        self.proof.update(operation='rollback', commit='d' * 40, release='d' * 40 + '-20261110000000')
        self.proof['images'].update(AIRFLOW=None, ETL_WORKER=None)
        self.assertEqual(request.verify_release(self.proof, self.payload, 'rollback')['commit'], 'd' * 40)
        self.proof['airflow'] = {'requested': 'on', 'phase': 'on'}
        with self.assertRaises(request.RequestError):
            request.verify_release(self.proof, self.payload, 'rollback')

    def test_missing_inputs_emit_failure_artifacts(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(sys, 'argv', ['production-request.py', 'deploy']):
            self.assertEqual(request.main(), 1)
        self.assertEqual(json.loads(Path('artifacts/production-release.json').read_text())['stage'], 'inputs')

    def test_wrapper_timeout_records_unconfirmed_health(self):
        run = subprocess.run

        def boundary(arguments, **kwargs):
            if arguments[0] != 'sudo':
                return run(arguments, **kwargs)
            if kwargs.get('input') == b'{"release_evidence_protocol":2}':
                return subprocess.CompletedProcess(arguments, 0,
                    b'{"release_evidence_protocol":2,"operation_seconds":1800,"recovery_seconds":1200}', b'')
            raise subprocess.TimeoutExpired(arguments, 3120, output=b'private-secret-fixture')

        with patch.dict(os.environ, self.environment), patch.object(sys, 'argv', ['production-request.py', 'deploy']), \
                patch.object(request.subprocess, 'run', side_effect=boundary):
            self.assertEqual(request.main(), 1)
        report = json.loads(Path('artifacts/production-release.json').read_text())
        self.assertEqual(report['error'], 'TimeoutExpired')
        self.assertEqual(json.loads(Path('artifacts/production-health.json').read_text())['status'], 'unconfirmed')

    def test_wrapper_receipt_reads_actual_manifest_and_lifecycle(self):
        root = self.directory / 'host'
        release = root / 'releases' / self.proof['release']
        release.mkdir(parents=True)
        manifest = {'commit': self.revision, 'config_sha256': self.payload['YUNESA_CONFIG_SHA256'],
                    'project': 'yunesa-app',
                    **{kind.lower() + '_image': self.proof['images'][kind] for kind in IMAGE_KINDS}}
        path = release / 'manifest.json'
        path.write_text(json.dumps(manifest))
        path.chmod(0o600)
        with patch.object(deployment, 'ROOT', root):
            proof = deployment.release_evidence(release, 'deploy', self.proof['readiness'])
        self.assertEqual(request.verify_release(proof, self.payload, 'deploy')['images'], self.proof['images'])

    def test_protocol_request_reads_trusted_config_without_creating_state(self):
        root = self.directory / 'protocol-host'
        root.mkdir(mode=0o700)
        for destination in TRUSTED_FILES.values():
            path = root / destination
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(destination)
        registry = root / 'config/registry.json'
        registry.write_text(json.dumps({'config_sha256': configuration_digest(root, installed=True)}))
        registry.chmod(0o600)
        output = io.StringIO()
        previous_umask = os.umask(0o077)
        try:
            with patch.object(deployment, 'ROOT', root), patch.object(sys, 'argv', ['deploy-production.py', 'deploy']), \
                    patch.object(sys, 'stdin', io.TextIOWrapper(io.BytesIO(b'{"release_evidence_protocol":2}'))), \
                    patch.object(sys, 'stdout', output):
                self.assertEqual(deployment.main(), 0)
        finally:
            os.umask(previous_umask)
        self.assertEqual(json.loads(output.getvalue()), {'release_evidence_protocol': 2,
                         'operation_seconds': 1800, 'recovery_seconds': 1200})
        self.assertFalse((root / 'shared').exists())
        self.assertFalse((root / 'releases').exists())
        self.assertFalse((root / 'diagnostics').exists())

    def test_validation_cli(self):
        result = subprocess.run([sys.executable, '-B', str(SOURCE / 'scripts/production-request.py'), 'deploy',
                                 '--validate-only'], env={**os.environ, **self.environment},
                                capture_output=True, check=True)
        self.assertEqual(json.loads(result.stdout)['operation'], 'deploy')
        self.assertNotIn('private-secret-fixture', result.stdout.decode())


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def records(self, execution):
        return [json.loads(line) for line in (self.root / 'diagnostics' / (execution.reference + '.jsonl')).read_text().splitlines()]

    def test_real_subprocess_deadline_allows_recovery_to_finish(self):
        marker = self.root / 'recovered'
        with self.assertRaises(deployment.DeployError):
            with deployment.ReleaseExecution(self.root, 'deploy', {}, 0.1, 1) as execution, \
                    patch.object(deployment, 'EXECUTION', execution):
                try:
                    deployment.phase('verification')
                    deployment.run([sys.executable, '-c', 'import time; time.sleep(5)'], label='Readiness', timeout=10)
                except deployment.DeployError as error:
                    execution.recover(error)
                    deployment.run([sys.executable, '-c',
                        'import time; from pathlib import Path; time.sleep(0.25); Path(' + repr(str(marker)) + ').write_text("done")'],
                        label='Restore current release', timeout=10)
                    execution.recovery_status = 'passed'
                    raise
        self.assertEqual(marker.read_text(), 'done')
        failure = execution.failure(deployment.DeployError('unused'))
        self.assertEqual(failure['category'], 'deadline')
        self.assertEqual(failure['stage'], 'verification')
        self.assertEqual(failure['recovery_status'], 'passed')
        self.assertEqual(self.records(execution)[-1]['recovery_status'], 'passed')

    def test_recovery_has_its_own_bounded_deadline(self):
        with self.assertRaisesRegex(deployment.DeployError, 'Recovery deadline'):
            with deployment.ReleaseExecution(self.root, 'rollback', {}, 0.05, 0.1) as execution, \
                    patch.object(deployment, 'EXECUTION', execution):
                try:
                    deployment.phase('activation')
                    time.sleep(1)
                except deployment.DeployError as error:
                    execution.recover(error)
                    deployment.run([sys.executable, '-c', 'import time; time.sleep(5)'], label='Recovery', timeout=10)
        failure = execution.failure(deployment.DeployError('unused'))
        self.assertEqual(failure['category'], 'recovery_deadline')
        self.assertEqual(failure['recovery_status'], 'deadline_exceeded')
        self.assertEqual(self.records(execution)[-1]['recovery_error']['category'], 'recovery_deadline')

    def test_sigterm_preserves_recovery_budget_on_repeated_signal(self):
        original_handler = signal.getsignal(signal.SIGTERM)
        with self.assertRaises(deployment.DeployError):
            with deployment.ReleaseExecution(self.root, 'deploy', {}, 1, 1) as execution:
                try:
                    execution.phase('activation')
                    os.kill(os.getpid(), signal.SIGTERM)
                except deployment.DeployError as error:
                    execution.recover(error)
                    os.kill(os.getpid(), signal.SIGTERM)
                    time.sleep(0.03)
                    execution.recovery_status = 'passed'
                    raise
        self.assertEqual(signal.getsignal(signal.SIGTERM), original_handler)
        self.assertEqual(execution.failure(deployment.DeployError('unused'))['category'], 'cancelled')
        self.assertEqual(execution.recovery_status, 'passed')

    def test_finalization_finishes_pointer_write_after_readiness(self):
        with deployment.ReleaseExecution(self.root, 'deploy', {}, 0.05, 1) as execution:
            execution.phase('finalization')
            time.sleep(0.1)
            os.kill(os.getpid(), signal.SIGTERM)
            (self.root / 'pointer-proof').write_text('committed')
        self.assertEqual(self.records(execution)[-1]['event'], 'verified')
        self.assertEqual((self.root / 'pointer-proof').read_text(), 'committed')

    def test_private_journal_redacts_credentials_and_has_private_permissions(self):
        secret = 'private-secret-with-"quotes"-and-\\slashes'
        with self.assertRaises(deployment.DeployError):
            with deployment.ReleaseExecution(self.root, 'deploy', {'GLOBAL_PASSWORD': secret}) as execution:
                execution.phase('activation')
                raise deployment.DeployError('Failed with ' + secret, category='command_failed')
        journal = self.root / 'diagnostics' / (execution.reference + '.jsonl')
        self.assertNotIn(secret, journal.read_text())
        self.assertIn('[redacted]', self.records(execution)[-1]['failure']['message'])
        self.assertEqual(journal.stat().st_mode & 0o777, 0o600)
        self.assertEqual(journal.parent.stat().st_mode & 0o777, 0o700)
        failure = execution.failure(deployment.DeployError('failed'))
        self.assertEqual(request.wrapper_failure(json.dumps(failure).encode())['diagnostic_reference'], execution.reference)

    def test_symlink_journal_directory_is_refused(self):
        target = self.root / 'other'
        target.mkdir()
        (self.root / 'diagnostics').symlink_to(target, target_is_directory=True)
        with self.assertRaises(deployment.DeployError):
            deployment.ReleaseExecution(self.root, 'deploy', {})
        self.assertEqual(list(target.iterdir()), [])

    def test_journal_io_failure_does_not_interrupt_recovery(self):
        with self.assertRaises(deployment.DeployError):
            with deployment.ReleaseExecution(self.root, 'deploy', {}) as execution:
                try:
                    raise deployment.DeployError('Candidate failed', category='command_failed')
                except deployment.DeployError as error:
                    execution.recover(error)
                    with patch.object(deployment.os, 'fsync', side_effect=OSError('storage unavailable')):
                        execution.event('recovery_progress')
                    (self.root / 'recovered').write_text('done')
                    execution.recovery_status = 'passed'
                    raise
        self.assertEqual((self.root / 'recovered').read_text(), 'done')
        self.assertIsNone(execution.failure(deployment.DeployError('unused'))['diagnostic_reference'])
        self.assertEqual(execution.recovery_status, 'passed')

    def test_quiescence_failure_remains_closed_without_false_recovery(self):
        with self.assertRaises(deployment.QuiescenceError):
            with deployment.ReleaseExecution(self.root, 'deploy', {}) as execution:
                execution.phase('quiescence')
                raise deployment.QuiescenceError('Drain did not complete', category='deadline')
        self.assertEqual(execution.recovery_status, 'quiescence_closed')
        self.assertEqual(self.records(execution)[-1]['recovery_status'], 'quiescence_closed')

    def test_main_failure_returns_reference_to_real_private_journal(self):
        for destination in TRUSTED_FILES.values():
            path = self.root / destination
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(destination)
        registry = self.root / 'config/registry.json'
        registry.write_text(json.dumps({'config_sha256': configuration_digest(self.root, installed=True)}))
        registry.chmod(0o600)
        stderr = io.StringIO()
        previous_umask = os.umask(0o077)
        try:
            with patch.object(deployment, 'ROOT', self.root), patch.object(sys, 'argv', ['deploy-production.py', 'deploy']), \
                    patch.object(sys, 'stdin', io.TextIOWrapper(io.BytesIO(b'{"SHELL":"private-secret-fixture"}'))), \
                    patch.object(sys, 'stderr', stderr):
                self.assertEqual(deployment.main(), 1)
        finally:
            os.umask(previous_umask)
        failure = request.wrapper_failure(stderr.getvalue().encode())
        journal = self.root / 'diagnostics' / (failure['diagnostic_reference'] + '.jsonl')
        self.assertTrue(journal.is_file())
        self.assertIn('Request contains unsupported fields', journal.read_text())
        self.assertNotIn('private-secret-fixture', stderr.getvalue())
        self.assertFalse((self.root / 'shared').exists())


if __name__ == '__main__':
    unittest.main()
