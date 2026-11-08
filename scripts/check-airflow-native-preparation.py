"""Exercise the real local controller with a simulated paid AWS boundary."""

from __future__ import annotations

import copy
import importlib.util
import hashlib
import json
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

from airflow_capacity_session import (
    AMI, PROTECTED_INSTANCES, Session, capacity_result, native_hardware, schedule_request, termination_policy, trust_policy,
)

spec = importlib.util.spec_from_file_location('native_controller', Path(__file__).with_name('airflow-native-controller.py'))
controller = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controller)


def lease() -> dict:
    started = time.time()
    return {'session': '0123456789abcdef', 'account_id': '000000000000', 'region': 'us-east-1',
        'instance_id': 'i-0123456789abcdef0', 'started_at': started, 'expires_at': started + 3600,
        'volume_id': 'vol-0123456789abcdef0', 'eni_id': 'eni-0123456789abcdef0',
        'security_group_id': 'sg-0123456789abcdef0', 'key_pair_id': 'key-0123456789abcdef0'}


class AwsBoundary:
    """Record EC2/IAM/Scheduler requests without creating external resources."""

    def __init__(self, value: dict):
        self.value = value
        self.session = Session.read(value)
        self.calls = []
        self.removed = set()
        self.denied = set()
        self.foreign = set()
        self.schedule = schedule_request(self.session)
        self.role_trust = trust_policy(self.session)
        self.tags = [{'Key': key, 'Value': value} for key, value in self.session.tags.items()]
        self.item = {'InstanceId': self.session.instance_id, 'InstanceType': 't4g.small', 'Architecture': 'arm64',
            'ImageId': AMI, 'State': {'Name': 'running'}, 'ClientToken': self.session.session,
            'LaunchTime': datetime.fromtimestamp(self.session.started_at, timezone.utc).isoformat(),
            'KeyName': self.session.name, 'Tags': copy.deepcopy(self.tags), 'PublicIpAddress': '192.0.2.1',
            'BlockDeviceMappings': [{'Ebs': {'VolumeId': value['volume_id'], 'DeleteOnTermination': True}}],
            'NetworkInterfaces': [{'NetworkInterfaceId': value['eni_id']}],
            'SecurityGroups': [{'GroupId': value['security_group_id']}]}
        self.unrelated = {'instance_id': 'i-fffffffffffffffff', 'state': 'running'}

    def call(self, service: str, action: str, payload: dict) -> dict:
        self.calls.append((service, action, copy.deepcopy(payload)))
        if action in self.denied:
            raise controller.AwsError('AccessDenied', service + '/' + action)
        tags = [] if action in self.foreign else self.tags
        if action == 'get-caller-identity':
            return {'Account': self.session.account_id}
        if action == 'describe-instances':
            return {'Reservations': [{'Instances': [copy.deepcopy(self.item)]}]}
        if action == 'describe-instance-attribute':
            return {'InstanceInitiatedShutdownBehavior': {'Value': 'terminate'}}
        if action == 'describe-addresses':
            return {'Addresses': []}
        if action == 'terminate-instances':
            if payload != {'InstanceIds': [self.session.instance_id]}:
                raise AssertionError('Termination targeted another resource')
            self.item['State']['Name'] = 'terminated'
            self.item['BlockDeviceMappings'] = []
            self.item['NetworkInterfaces'] = []
            self.item['SecurityGroups'] = []
            return {}
        if action == 'describe-volumes':
            return {'Volumes': []}
        if action == 'describe-network-interfaces':
            return {'NetworkInterfaces': []}
        missing = {'get-schedule': 'ResourceNotFoundException', 'describe-security-groups': 'InvalidGroup.NotFound',
                   'describe-key-pairs': 'InvalidKeyPairID.NotFound', 'get-role': 'NoSuchEntity'}
        if action in self.removed:
            raise controller.AwsError(missing[action], service + '/' + action)
        if action == 'get-schedule':
            return self.schedule
        if action == 'get-role-policy':
            return {'PolicyDocument': termination_policy(self.session)}
        if action == 'get-role':
            return {'Role': {'Arn': self.session.role_arn, 'Tags': tags,
                             'AssumeRolePolicyDocument': self.role_trust}}
        if action == 'describe-security-groups':
            return {'SecurityGroups': [{'GroupName': self.session.name, 'Tags': tags}]}
        if action == 'describe-key-pairs':
            return {'KeyPairs': [{'KeyName': self.session.name, 'Tags': tags}]}
        delete = {'delete-schedule': 'get-schedule', 'delete-security-group': 'describe-security-groups',
                  'delete-key-pair': 'describe-key-pairs', 'delete-role': 'get-role'}
        if action in delete:
            self.removed.add(delete[action])
            return {}
        if action == 'delete-role-policy':
            return {}
        raise AssertionError('Unimplemented AWS boundary ' + action)


class NativePreparationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='yunesa-native-check-')
        self.addCleanup(self.directory.cleanup)
        self.output = Path(self.directory.name)
        self.value = lease()
        self.aws = AwsBoundary(self.value)
        self.guest_checked = []

    def guest(self, value: dict, session: Session, ip: str) -> None:
        self.guest_checked.append(ip)

    def subject(self):
        return controller.Controller(self.value, self.aws, self.output / 'receipt.json', self.guest)

    def test_native_two_cpu_and_signed_ram_difference(self):
        session = Session.read(self.value)
        identity = {'accountId': session.account_id, 'instanceId': session.instance_id,
            'region': session.region, 'instanceType': 't4g.small', 'architecture': 'arm64', 'imageId': AMI}
        native_hardware({'architecture': 'aarch64', 'cpu_count': 2, 'mem_total_kib': 1_879_088}, session, identity)
        for key, wrong in [('cpu_count', 8), ('architecture', 'x86_64'), ('mem_total_kib', 2_000_000)]:
            hardware = {'architecture': 'aarch64', 'cpu_count': 2, 'mem_total_kib': 1_879_024, key: wrong}
            with self.subTest(key=key), self.assertRaises(ValueError):
                native_hardware(hardware, session, identity)
        identity['instanceId'] = next(iter(PROTECTED_INSTANCES))
        with self.assertRaises(ValueError):
            session.check_identity(identity)

    def test_production_and_extended_leases_rejected(self):
        for identifier in PROTECTED_INSTANCES:
            with self.subTest(instance=identifier), self.assertRaises(ValueError):
                Session.read({**self.value, 'instance_id': identifier})
        with self.assertRaises(ValueError):
            Session.read({**self.value, 'expires_at': self.value['expires_at'] + 1})
        with self.assertRaises(ValueError):
            Session.read({**self.value, 'started_at': float('nan')})

    def test_capacity_artifact_contract(self):
        session = Session.read(self.value)
        value = {'hardware': {'fixture_identity': {'accountId': session.account_id,
            'instanceId': session.instance_id, 'region': session.region, 'instanceType': 't4g.small',
            'architecture': 'arm64', 'imageId': AMI}}, 'run_state': 'success', 'workers': [],
            'destination': {'nodes': 4, 'relationships': 5}, 'post_off_available_increase_bytes': 1024,
            'observed_worker_peak_so_far_bytes': {'fixture_task': 1024}, 'application_cycles': 2,
            'restart_deltas': {'fixture_core': 0}}
        capacity_result(value, session)
        for key, invalid in [('run_state', 'failed'), ('workers', ['active']),
                             ('post_off_available_increase_bytes', 0),
                             ('observed_worker_peak_so_far_bytes', {}), ('application_cycles', 0),
                             ('restart_deltas', {'fixture_core': 1})]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                capacity_result({**value, key: invalid}, session)

    def test_receipt_from_another_session_is_rejected(self):
        (self.output / 'receipt.json').write_text(json.dumps({'session': 'foreign', 'instance_id': self.value['instance_id']}))
        with self.assertRaises(ValueError):
            self.subject()
        self.assertEqual(self.aws.calls, [])

    def test_real_process_success_then_complete_cleanup(self):
        item = self.subject()
        self.assertEqual(item.supervise([sys.executable, '-c', 'print("actual child entrypoint")']), 0)
        self.assertTrue(item.result['cleanup_complete'])
        self.assertEqual(self.guest_checked, ['192.0.2.1'])
        self.assertIn('actual child entrypoint', (self.output / 'receipt.workload.log').read_text())
        self.assertEqual(self.aws.unrelated['state'], 'running')

    def test_workload_failure_still_cleans(self):
        item = self.subject()
        self.assertEqual(item.supervise([sys.executable, '-c', 'raise SystemExit(7)']), 7)
        self.assertTrue(item.result['cleanup_complete'])

    def test_real_process_deadline_near_end_of_hour(self):
        self.value['started_at'] = time.time() - 3058
        self.value['expires_at'] = self.value['started_at'] + 3600
        self.aws = AwsBoundary(self.value)
        item = self.subject()
        started = time.monotonic()
        with self.assertRaises(TimeoutError):
            item.supervise([sys.executable, '-c', 'import time; time.sleep(30)'])
        self.assertLess(time.monotonic() - started, 12)
        self.assertTrue(item.result['cleanup_complete'])
        self.assertIn('local_process_stopped', [event['phase'] for event in item.result['events']])

    def test_expired_session_cleans_without_starting_work(self):
        self.value['started_at'] -= 3601
        self.value['expires_at'] -= 3601
        self.aws = AwsBoundary(self.value)
        item = self.subject()
        with self.assertRaises(TimeoutError):
            item.supervise([sys.executable, '-c', 'raise AssertionError("must not start")'])
        self.assertNotIn('workload_started', [event['phase'] for event in item.result['events']])
        self.assertTrue(item.result['cleanup_complete'])

    def test_wrong_instance_tags_prevent_all_cloud_mutation(self):
        self.aws.item['Tags'] = []
        with self.assertRaises(ValueError):
            self.subject().supervise([sys.executable, '-c', 'print("must not start")'])
        self.assertFalse(any(action.startswith(('delete-', 'terminate-')) for _, action, _ in self.aws.calls))

    def test_missing_aws_watchdog_prevents_work_and_cleans(self):
        self.aws.removed.add('get-schedule')
        item = self.subject()
        with self.assertRaises(controller.AwsError):
            item.supervise([sys.executable, '-c', 'print("must not start")'])
        self.assertTrue(item.result['cleanup_complete'])
        self.assertNotIn('workload_started', [event['phase'] for event in item.result['events']])

    def test_wrong_schedule_deadline_prevents_work(self):
        self.aws.schedule['ScheduleExpression'] = 'at(2099-01-01T00:00:00)'
        with self.assertRaises(ValueError):
            self.subject().supervise([sys.executable, '-c', 'print("must not start")'])
        self.assertEqual(self.aws.item['State']['Name'], 'terminated')

    def test_wrong_iam_trust_prevents_work(self):
        self.aws.role_trust = {}
        with self.assertRaises(ValueError):
            self.subject().supervise([sys.executable, '-c', 'print("must not start")'])
        self.assertEqual(self.aws.item['State']['Name'], 'terminated')

    def test_guest_watchdog_failure_prevents_work(self):
        def unavailable(*args):
            raise RuntimeError('SSH guest watchdog unavailable')
        item = controller.Controller(self.value, self.aws, self.output / 'receipt.json', unavailable)
        with self.assertRaises(RuntimeError):
            item.supervise([sys.executable, '-c', 'print("must not start")'])
        self.assertTrue(item.result['cleanup_complete'])

    def test_cleanup_is_idempotent(self):
        item = self.subject()
        item.cleanup()
        item.cleanup()
        self.assertTrue(item.result['cleanup_complete'])
        self.assertEqual(sum(action == 'terminate-instances' for _, action, _ in self.aws.calls), 1)

    def test_access_denied_is_not_absence(self):
        self.aws.denied.add('describe-volumes')
        item = self.subject()
        with self.assertRaises(RuntimeError):
            item.cleanup()
        self.assertFalse(item.result['cleanup_complete'])
        self.assertIn('AccessDenied', json.dumps(item.result))

    def test_interrupt_still_cleans(self):
        def interrupted(*args):
            raise KeyboardInterrupt('Operator cancelled SSH verification')
        item = controller.Controller(self.value, self.aws, self.output / 'receipt.json', interrupted)
        with self.assertRaises(KeyboardInterrupt):
            item.supervise([sys.executable, '-c', 'print("must not start")'])
        self.assertTrue(item.result['cleanup_complete'])

    def test_private_key_removed_only_with_matching_path_and_hash(self):
        directory = self.output / self.aws.session.name
        directory.mkdir()
        path = directory / 'fixture_ed25519'
        path.write_bytes(b'synthetic private-key cleanup fixture')
        self.value['ssh'] = {'key': str(path), 'key_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        self.subject().cleanup()
        self.assertFalse(path.exists())
        path.write_bytes(b'changed file must survive')
        with self.assertRaises(RuntimeError):
            self.subject().cleanup()
        self.assertTrue(path.exists())

    def test_private_key_outside_receipt_scope_is_preserved(self):
        path = self.output / 'unrelated-key'
        path.write_bytes(b'preserve unrelated local file')
        self.value['ssh'] = {'key': str(path), 'key_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        with self.assertRaises(RuntimeError):
            self.subject().cleanup()
        self.assertTrue(path.exists())

    def test_partial_cleanup_can_resume(self):
        self.aws.denied.add('delete-role')
        item = self.subject()
        with self.assertRaises(RuntimeError):
            item.cleanup()
        self.assertFalse(item.result['cleanup_complete'])
        self.aws.denied.clear()
        item = self.subject()
        item.cleanup()
        self.assertTrue(item.result['cleanup_complete'])

    def test_completed_workload_cannot_be_replayed(self):
        self.subject().supervise([sys.executable, '-c', 'print("one attempt")'])
        item = self.subject()
        with self.assertRaises(ValueError):
            item.supervise([sys.executable, '-c', 'print("must not replay")'])
        self.assertEqual(sum(event['phase'] == 'workload_started' for event in item.result['events']), 1)

    def test_primary_failure_survives_cleanup_failure(self):
        self.aws.denied.add('describe-volumes')
        def unavailable(*args):
            raise RuntimeError('Original SSH verification failure')
        item = controller.Controller(self.value, self.aws, self.output / 'receipt.json', unavailable)
        with self.assertRaisesRegex(RuntimeError, 'Original SSH verification failure') as context:
            item.supervise([sys.executable, '-c', 'print("must not start")'])
        self.assertIn('Cleanup also failed', str(context.exception.__notes__))
        self.assertFalse(item.result['cleanup_complete'])

    def test_foreign_ancillary_resources_are_preserved(self):
        self.aws.foreign.update(['describe-security-groups', 'describe-key-pairs', 'get-role'])
        item = self.subject()
        with self.assertRaises(RuntimeError):
            item.cleanup()
        forbidden = {'delete-security-group', 'delete-key-pair', 'delete-role-policy', 'delete-role'}
        self.assertFalse(any(action in forbidden for _, action, _ in self.aws.calls))
        self.assertEqual(self.aws.item['State']['Name'], 'terminated')

    def test_local_cli_render_and_mutation_gate(self):
        path = self.output / 'lease.json'
        path.write_text(json.dumps(self.value))
        args = [sys.executable, str(Path(controller.__file__)), '--lease', str(path), '--output', str(self.output / 'render')]
        result = subprocess.run([*args, 'render'], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('RENDERED_OFFLINE', result.stdout)
        expected = schedule_request(Session.read(self.value))
        self.assertEqual(json.loads((self.output / 'render/schedule.json').read_text()), expected)
        result = subprocess.run([*args, 'cleanup'], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertIn('--allow-cloud-cleanup', result.stderr)

    def test_aws_cli_cannot_launch_or_create_resources(self):
        with self.assertRaises(ValueError):
            controller.AwsCli('us-east-1').call('ec2', 'run-instances', {})
        with self.assertRaises(ValueError):
            controller.AwsCli('us-east-1').call('scheduler', 'create-schedule', {})


if __name__ == '__main__':
    unittest.main(verbosity=2)
