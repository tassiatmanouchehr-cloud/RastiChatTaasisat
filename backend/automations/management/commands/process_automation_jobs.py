"""Idempotent, concurrency-safe processor for delayed automation actions
(ScheduledAction rows created by the SCHEDULE_ACTION action — spec section 6).

Run on a schedule (cron, or later a Celery beat task — deliberately
framework-agnostic so it drops into either) via:

    python manage.py process_automation_jobs

Each due job is claimed with SELECT ... FOR UPDATE SKIP LOCKED (Postgres)
inside its own short transaction and immediately flipped to RUNNING before
the lock is released, so two overlapping worker processes can never claim —
and therefore never execute — the same job twice. The actual action runs
outside that transaction (so a slow domain-service call never holds a
row lock); RUNNING already keeps every other worker out in the meantime.
A job that fails is returned to PENDING for a future retry until
`max_attempts` is reached, at which point it is permanently FAILED.
"""
import os
import socket
import uuid

from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.utils import timezone

from automations.actions import ActionError, execute_action
from automations.engine import ActionRunContext
from automations.events import AutomationActionContext
from automations.models import AutomationActionExecution, AutomationExecution, AutomationRule, ScheduledAction


class Command(BaseCommand):
    help = 'Execute due ScheduledAction rows (delayed automation actions).'

    def add_arguments(self, parser):
        parser.add_argument('--batch-size', type=int, default=200)

    def handle(self, *args, **options):
        worker_id = f'{socket.gethostname()}:{os.getpid()}'
        now = timezone.now()
        supports_skip_locked = connection.features.has_select_for_update_skip_locked

        due_ids = list(
            ScheduledAction.objects.filter(
                status=ScheduledAction.Status.PENDING, execute_at__lte=now,
            ).order_by('execute_at').values_list('id', flat=True)[:options['batch_size']]
        )

        processed = succeeded = failed = skipped = 0

        for job_id in due_ids:
            job = self._claim(job_id, worker_id, now, supports_skip_locked)
            if job is None:
                continue  # already claimed by a concurrent worker, or no longer pending
            processed += 1
            outcome = self._run_job(job)
            if outcome == 'succeeded':
                succeeded += 1
            elif outcome == 'skipped':
                skipped += 1
            else:
                failed += 1

        self.stdout.write(self.style.SUCCESS(
            f'Processed {processed} scheduled action(s): {succeeded} succeeded, {failed} failed, {skipped} skipped.'
        ))

    @staticmethod
    def _claim(job_id, worker_id, now, supports_skip_locked):
        with transaction.atomic():
            qs = ScheduledAction.objects.select_for_update(skip_locked=supports_skip_locked)
            try:
                job = qs.get(pk=job_id, status=ScheduledAction.Status.PENDING)
            except ScheduledAction.DoesNotExist:
                return None
            job.status = ScheduledAction.Status.RUNNING
            job.locked_at = now
            job.locked_by = worker_id
            job.attempts += 1
            job.save(update_fields=['status', 'locked_at', 'locked_by', 'attempts'])
        return job

    def _run_job(self, job):
        if job.conversation_id is None:
            self._finish(job, ScheduledAction.Status.SKIPPED, error='Conversation no longer exists.')
            return 'skipped'

        from conversations.models import Conversation
        conv = Conversation.objects.select_related(
            'workspace', 'visitor', 'assigned_to', 'team', 'queue', 'sla', 'sla__policy', 'sla__policy__calendar',
        ).filter(id=job.conversation_id).first()
        if conv is None:
            self._finish(job, ScheduledAction.Status.SKIPPED, error='Conversation no longer exists.')
            return 'skipped'

        execution = AutomationExecution.objects.create(
            workspace=job.workspace, rule=job.rule, rule_name_snapshot=job.rule.name if job.rule_id else '',
            trigger_type=AutomationRule.Trigger.SCHEDULED_TIME_REACHED, event_id=uuid.uuid4(),
            correlation_id=job.correlation_id, depth=job.depth, conversation=conv,
            status=AutomationExecution.Status.MATCHED, condition_result=True, actor_type='SYSTEM',
        )
        action_type = job.action_definition.get('type', '')
        run_ctx = ActionRunContext(
            execution_id=execution.id, rule_id=str(job.rule_id) if job.rule_id else '',
            correlation_id=job.correlation_id, depth=job.depth, action_index=0,
        )

        try:
            with AutomationActionContext(job.correlation_id, job.depth):
                result, obj_type, obj_id = execute_action(conv, job.action_definition, run_ctx)
            AutomationActionExecution.objects.create(
                execution=execution, action_index=0, action_type=action_type,
                status=AutomationActionExecution.Status.SUCCEEDED, result_summary=result,
                affected_object_type=obj_type, affected_object_id=obj_id,
            )
            execution.status = AutomationExecution.Status.SUCCEEDED
            execution.save(update_fields=['status'])
            self._finish(job, ScheduledAction.Status.SUCCEEDED)
            return 'succeeded'
        except ActionError as exc:
            return self._fail(job, execution, action_type, str(exc)[:500])
        except Exception:
            return self._fail(job, execution, action_type, 'Internal error while running this scheduled action.')

    @staticmethod
    def _fail(job, execution, action_type, error):
        AutomationActionExecution.objects.create(
            execution=execution, action_index=0, action_type=action_type,
            status=AutomationActionExecution.Status.FAILED, error_summary=error,
        )
        execution.status = AutomationExecution.Status.FAILED
        execution.error_summary = error
        execution.save(update_fields=['status', 'error_summary'])

        if job.attempts >= job.max_attempts:
            ScheduledAction.objects.filter(pk=job.pk).update(
                status=ScheduledAction.Status.FAILED, last_error=error, locked_at=None, locked_by='',
            )
        else:
            # Retryable: back to PENDING so a future run picks it up again.
            ScheduledAction.objects.filter(pk=job.pk).update(
                status=ScheduledAction.Status.PENDING, last_error=error, locked_at=None, locked_by='',
            )
        return 'failed'

    @staticmethod
    def _finish(job, status_value, error=''):
        fields = {'status': status_value, 'locked_at': None, 'locked_by': ''}
        if error:
            fields['last_error'] = error
        if status_value == ScheduledAction.Status.SUCCEEDED:
            fields['executed_at'] = timezone.now()
        ScheduledAction.objects.filter(pk=job.pk).update(**fields)
