import redis as redis_client
from django.conf import settings
from django.db import connections
from django.db.migrations.executor import MigrationExecutor
from rest_framework.response import Response
from rest_framework.views import APIView


def _check_database():
    try:
        connections['default'].cursor()
        return True, None
    except Exception as exc:  # noqa: BLE001 - health check must never itself crash
        return False, str(exc)[:200]


def _check_redis():
    """Pings the SAME Redis instance/credentials Channels uses (see
    settings.REDIS_CONNECTION), not Django's cache framework — this project
    has no CACHES backend configured, so a `django.core.cache.cache` probe
    would have silently exercised the in-process LocMemCache and always
    reported "up" even with Redis completely down.
    """
    try:
        conn = redis_client.Redis(
            host=settings.REDIS_CONNECTION['host'],
            port=settings.REDIS_CONNECTION['port'],
            password=settings.REDIS_CONNECTION['password'],
            db=settings.REDIS_CONNECTION['db'],
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        conn.ping()
        return True, None
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)[:200]


def _check_migrations():
    try:
        executor = MigrationExecutor(connections['default'])
        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        return (len(plan) == 0), len(plan)
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)[:200]


class LivenessView(APIView):
    """Answers only "is this process alive and able to handle a request at
    all" — no dependency checks. A container orchestrator restarts the
    process on liveness failure, so this must never fail because of a
    transient DB/Redis outage (that's what readiness is for); it should only
    ever fail if the process itself is wedged.
    """
    permission_classes = []

    def get(self, request):
        return Response({'status': 'alive'})


class ReadinessView(APIView):
    """Answers "can this process correctly serve traffic right now" — used
    to gate whether a load balancer/orchestrator sends it requests. Must
    never report ready when the database or Redis (the Channels/WebSocket
    backend) is unreachable, or when the schema doesn't match the code
    (unapplied migrations) — serving traffic in either state would fail
    requests or corrupt data, not just look nice on a dashboard.
    """
    permission_classes = []

    def get(self, request):
        db_ok, db_error = _check_database()
        redis_ok, redis_error = _check_redis()
        migrations_ok, migrations_detail = _check_migrations()

        ready = db_ok and redis_ok and migrations_ok
        body = {
            'status': 'ready' if ready else 'not_ready',
            'components': {
                'database': {'up': db_ok, **({'error': db_error} if db_error else {})},
                'redis': {'up': redis_ok, **({'error': redis_error} if redis_error else {})},
                'migrations': {
                    'up_to_date': migrations_ok,
                    **({'pending_count': migrations_detail} if migrations_ok else {'error': migrations_detail}),
                },
            },
        }
        return Response(body, status=200 if ready else 503)


class HealthCheckView(APIView):
    """Kept at its original path/shape (`/api/v1/health/`) for backward
    compatibility with anything already polling it; equivalent to
    ReadinessView's dependency checks, without the migration-state detail.
    """
    permission_classes = []

    def get(self, request):
        db_ok, db_error = _check_database()
        redis_ok, redis_error = _check_redis()
        ready = db_ok and redis_ok
        health = {
            'status': 'healthy' if ready else 'unhealthy',
            'components': {
                'database': 'up' if db_ok else 'down',
                'redis': 'up' if redis_ok else 'down',
            },
        }
        return Response(health, status=200 if ready else 503)
