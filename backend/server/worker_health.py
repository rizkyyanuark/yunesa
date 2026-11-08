"""Check the ARQ heartbeat without importing application job handlers."""

import asyncio
import os
import sys

from arq.connections import RedisSettings
from arq.worker import async_check_health
from redis.exceptions import RedisError


def main() -> int:
    try:
        settings = RedisSettings.from_dsn(os.getenv('REDIS_URL', 'redis://redis:6379/0'))
        return asyncio.run(async_check_health(settings))
    except (RedisError, OSError, ValueError, RuntimeError) as error:
        print(f'Worker heartbeat check failed ({type(error).__name__})', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
