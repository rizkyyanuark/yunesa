"""Validate the disposable EC2 identity and share its absolute deadlines."""

from __future__ import annotations

import json
import math
import re
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone

PROTECTED_INSTANCES = {'i-04ba2d1b2dcd7f757', 'i-0571d58c00a33db88', 'i-0808bc172b784c258'}
TARGET_MEM_KIB = 1_879_024
AMI = 'ami-0bec8cef5313300ad'
PURPOSE = 'yunesa-task-6-3'


@dataclass(frozen=True)
class Session:
    session: str
    account_id: str
    instance_id: str
    started_at: float
    expires_at: float
    region: str = 'us-east-1'

    @classmethod
    def read(cls, value: dict) -> Session:
        result = cls(**{name: value[name] for name in cls.__dataclass_fields__})
        if not re.fullmatch(r'[a-f0-9]{16}', result.session):
            raise ValueError('Invalid fixture session')
        if not re.fullmatch(r'\d{12}', result.account_id) or result.region != 'us-east-1':
            raise ValueError('Unexpected AWS account or region')
        if (not re.fullmatch(r'i-[a-f0-9]{17}', result.instance_id)
                or result.instance_id in PROTECTED_INSTANCES):
            raise ValueError('Instance is invalid or protected')
        if (not all(math.isfinite(v) for v in (result.started_at, result.expires_at))
                or result.expires_at - result.started_at != 3600):
            raise ValueError('Fixture lifetime must be exactly one hour')
        if result.started_at > time.time() + 60:
            raise ValueError('Fixture clock is ahead of this controller')
        return result

    @property
    def name(self) -> str:
        return 'yunesa-6-3-' + self.session

    @property
    def role_arn(self) -> str:
        return f'arn:aws:iam::{self.account_id}:role/{self.name}'

    @property
    def instance_arn(self) -> str:
        return f'arn:aws:ec2:{self.region}:{self.account_id}:instance/{self.instance_id}'

    @property
    def tags(self) -> dict[str, str]:
        return {'Purpose': PURPOSE, 'Session': self.session, 'ExpiresAt': str(int(self.expires_at))}

    def remaining(self, minute: int) -> int:
        seconds = math.floor(self.started_at + minute * 60 - time.time())
        if seconds <= 0:
            raise TimeoutError(f'Fixture minute {minute} deadline exceeded')
        return seconds

    def check_tags(self, tags: list[dict]) -> None:
        observed = {item['Key']: item['Value'] for item in tags}
        if any(observed.get(key) != value for key, value in self.tags.items()):
            raise ValueError('Resource does not belong to this fixture session')

    def check_identity(self, identity: dict) -> None:
        expected = {'accountId': self.account_id, 'instanceId': self.instance_id,
                    'region': self.region, 'instanceType': 't4g.small',
                    'architecture': 'arm64', 'imageId': AMI}
        if any(identity.get(key) != value for key, value in expected.items()):
            raise ValueError('Native instance identity does not match the fixture lease')


def native_hardware(value: dict, session: Session, identity: dict) -> None:
    session.remaining(60)
    session.check_identity(identity)
    if value['architecture'] != 'aarch64' or value['cpu_count'] != 2:
        raise ValueError('Native capacity requires ARM64 and two vCPUs')
    if abs(value['mem_total_kib'] - TARGET_MEM_KIB) > 4096:
        raise ValueError('Native RAM differs from the audited Yunesa baseline')


def capacity_result(value: dict, session: Session) -> None:
    session.check_identity(value['hardware']['fixture_identity'])
    if (value['run_state'] != 'success' or value['workers']
            or value['destination']['nodes'] != 4 or value['destination']['relationships'] != 5
            or value['post_off_available_increase_bytes'] <= 0
            or not value['observed_worker_peak_so_far_bytes']
            or value['application_cycles'] < 1 or any(value['restart_deltas'].values())):
        raise ValueError('Native capacity result does not meet the acceptance contract')


def instance_identity() -> dict:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    base = 'http://169.254.169.254/latest/'
    request = urllib.request.Request(base + 'api/token', method='PUT',
        headers={'X-aws-ec2-metadata-token-ttl-seconds': '60'})
    with opener.open(request, timeout=3) as response:
        token = response.read().decode()
    request = urllib.request.Request(base + 'dynamic/instance-identity/document',
        headers={'X-aws-ec2-metadata-token': token})
    with opener.open(request, timeout=3) as response:
        return json.load(response)


def termination_policy(session: Session) -> dict:
    return {'Version': '2012-10-17', 'Statement': [{'Effect': 'Allow',
        'Action': 'ec2:TerminateInstances', 'Resource': session.instance_arn,
        'Condition': {'StringEquals': {'ec2:ResourceTag/' + key: value for key, value in session.tags.items()}}}]}


def trust_policy(session: Session) -> dict:
    return {'Version': '2012-10-17', 'Statement': [{'Effect': 'Allow',
        'Principal': {'Service': 'scheduler.amazonaws.com'}, 'Action': 'sts:AssumeRole',
        'Condition': {'StringEquals': {'aws:SourceAccount': session.account_id},
                      'ArnEquals': {'aws:SourceArn':
                          f'arn:aws:scheduler:{session.region}:{session.account_id}:schedule-group/default'}}}]}


def schedule_request(session: Session) -> dict:
    stamp = datetime.fromtimestamp(session.started_at + 55 * 60, timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
    return {'Name': session.name, 'GroupName': 'default', 'ClientToken': session.session,
        'ScheduleExpression': f'at({stamp})', 'ScheduleExpressionTimezone': 'UTC',
        'FlexibleTimeWindow': {'Mode': 'OFF'}, 'State': 'ENABLED', 'ActionAfterCompletion': 'DELETE',
        'Target': {'Arn': 'arn:aws:scheduler:::aws-sdk:ec2:terminateInstances',
                   'RoleArn': session.role_arn, 'Input': json.dumps({'InstanceIds': [session.instance_id]}),
                   'RetryPolicy': {'MaximumRetryAttempts': 2, 'MaximumEventAgeInSeconds': 120}}}


def watchdog_units(session: Session) -> dict[str, str]:
    stamp = datetime.fromtimestamp(session.started_at + 54 * 60, timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    return {session.name + '.service': '\n'.join([
        '[Unit]', 'Description=Terminate the disposable capacity fixture at its deadline',
        '[Service]', 'Type=oneshot', 'ExecStart=/usr/bin/systemctl --no-block poweroff', '']),
        session.name + '.timer': '\n'.join(['[Unit]', 'Description=Disposable capacity fixture deadline',
        '[Timer]', 'OnCalendar=' + stamp, 'AccuracySec=1s', 'RandomizedDelaySec=0',
        'Persistent=true', '[Install]', 'WantedBy=timers.target', ''])}
