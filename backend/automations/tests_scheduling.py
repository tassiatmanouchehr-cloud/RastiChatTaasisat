import uuid

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from .models import AutomationExecution, AutomationRule, ScheduledAction
from .scheduling import schedule_action
from .tests_base import AutomationTestMixin


class ScheduleActionCreationTests(TestCase, AutomationTestMixin):
    def setUp(self):
        self.ws, self.project, self.visitor, self.conv = self.make_full_stack()

    def test_creates_a_pending_row(self):
        scheduled = schedule_action(
            workspace=self.ws, rule_id=None, conversation=self.conv,
            action_definition={'type': 'ESCALATE', 'params': {}}, execute_at=timezone.now() + timezone.timedelta(minutes=5),
            correlation_id=uuid.uuid4(), depth=0, idempotency_seed='seed-1',
        )
        self.assertEqual(scheduled.status, ScheduledAction.Status.PENDING)

    def test_same_seed_is_idempotent(self):
        kwargs = dict(
            workspace=self.ws, rule_id=None, conversation=self.conv,
            action_definition={'type': 'ESCALATE', 'params': {}}, execute_at=timezone.now() + timezone.timedelta(minutes=5),
            correlation_id=uuid.uuid4(), depth=0, idempotency_seed='same-seed',
        )
        first = schedule_action(**kwargs)
        second = schedule_action(**kwargs)
        self.assertEqual(first.id, second.id)
        self.assertEqual(ScheduledAction.objects.count(), 1)

    def test_different_seed_creates_a_distinct_row(self):
        base = dict(
            workspace=self.ws, rule_id=None, conversation=self.conv,
            action_definition={'type': 'ESCALATE', 'params': {}}, execute_at=timezone.now() + timezone.timedelta(minutes=5),
            correlation_id=uuid.uuid4(), depth=0,
        )
        schedule_action(idempotency_seed='seed-a', **base)
        schedule_action(idempotency_seed='seed-b', **base)
        self.assertEqual(ScheduledAction.objects.count(), 2)


class ProcessAutomationJobsCommandTests(TestCase, AutomationTestMixin):
    def setUp(self):
        self.ws, self.project, self.visitor, self.conv = self.make_full_stack()

    def _due_job(self, action_definition, max_attempts=3, execute_at=None):
        return ScheduledAction.objects.create(
            workspace=self.ws, conversation=self.conv, action_definition=action_definition,
            correlation_id=uuid.uuid4(), depth=0, execute_at=execute_at or (timezone.now() - timezone.timedelta(minutes=1)),
            status=ScheduledAction.Status.PENDING, max_attempts=max_attempts,
        )

    def test_executes_a_due_job_and_marks_it_succeeded(self):
        job = self._due_job({'type': 'SET_PRIORITY', 'params': {'priority': 'URGENT'}})
        call_command('process_automation_jobs')
        job.refresh_from_db()
        self.conv.refresh_from_db()
        self.assertEqual(job.status, ScheduledAction.Status.SUCCEEDED)
        self.assertIsNotNone(job.executed_at)
        self.assertEqual(self.conv.priority, 'URGENT')
        self.assertTrue(AutomationExecution.objects.filter(
            trigger_type=AutomationRule.Trigger.SCHEDULED_TIME_REACHED, status=AutomationExecution.Status.SUCCEEDED,
        ).exists())

    def test_future_job_is_left_untouched(self):
        job = self._due_job({'type': 'ESCALATE', 'params': {}}, execute_at=timezone.now() + timezone.timedelta(hours=1))
        call_command('process_automation_jobs')
        job.refresh_from_db()
        self.assertEqual(job.status, ScheduledAction.Status.PENDING)
        self.assertEqual(job.attempts, 0)

    def test_already_running_job_is_not_reclaimed(self):
        job = self._due_job({'type': 'ESCALATE', 'params': {}})
        job.status = ScheduledAction.Status.RUNNING
        job.save(update_fields=['status'])
        call_command('process_automation_jobs')
        job.refresh_from_db()
        self.assertEqual(job.status, ScheduledAction.Status.RUNNING)  # untouched, not re-run

    def test_failed_job_retries_until_max_attempts_then_permanently_fails(self):
        job = self._due_job({'type': 'ASSIGN_TO_AGENT', 'params': {'agent_id': '00000000-0000-0000-0000-000000000000'}}, max_attempts=2)
        call_command('process_automation_jobs')
        job.refresh_from_db()
        self.assertEqual(job.status, ScheduledAction.Status.PENDING)  # 1st attempt failed, retryable
        self.assertEqual(job.attempts, 1)

        job.execute_at = timezone.now() - timezone.timedelta(minutes=1)
        job.save(update_fields=['execute_at'])
        call_command('process_automation_jobs')
        job.refresh_from_db()
        self.assertEqual(job.status, ScheduledAction.Status.FAILED)  # 2nd attempt exhausted max_attempts
        self.assertEqual(job.attempts, 2)

    def test_job_with_no_conversation_is_skipped_not_crashed(self):
        job = ScheduledAction.objects.create(
            workspace=self.ws, conversation=None, action_definition={'type': 'ESCALATE', 'params': {}},
            correlation_id=uuid.uuid4(), depth=0, execute_at=timezone.now() - timezone.timedelta(minutes=1),
            status=ScheduledAction.Status.PENDING,
        )
        call_command('process_automation_jobs')
        job.refresh_from_db()
        self.assertEqual(job.status, ScheduledAction.Status.SKIPPED)

    def test_cancelled_job_is_never_picked_up(self):
        job = self._due_job({'type': 'ESCALATE', 'params': {}})
        job.status = ScheduledAction.Status.CANCELLED
        job.save(update_fields=['status'])
        call_command('process_automation_jobs')
        job.refresh_from_db()
        self.assertEqual(job.status, ScheduledAction.Status.CANCELLED)
        self.assertEqual(job.attempts, 0)

    def test_running_command_twice_does_not_double_execute(self):
        job = self._due_job({'type': 'SET_PRIORITY', 'params': {'priority': 'URGENT'}})
        call_command('process_automation_jobs')
        call_command('process_automation_jobs')
        job.refresh_from_db()
        self.assertEqual(job.status, ScheduledAction.Status.SUCCEEDED)
        self.assertEqual(
            AutomationExecution.objects.filter(trigger_type=AutomationRule.Trigger.SCHEDULED_TIME_REACHED).count(), 1,
        )
