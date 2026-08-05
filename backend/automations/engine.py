"""Rule evaluation and action execution orchestration.

Deterministic policies (spec section 8):

- Rules for one event are evaluated in `priority` ascending, `created_at`
  ascending order (ties broken by creation time — stable regardless of
  dict/queryset iteration order).
- Every rule evaluated for a given event sees the SAME conversation
  snapshot, fetched exactly once at the start of process_event() — a
  rule's actions are not re-observed by a *later* rule's conditions within
  the same event-processing pass. This is simpler, fully deterministic,
  and avoids the "repeated customer-context fetches per rule" performance
  trap the spec explicitly warns about. Actions still take real effect in
  the database immediately (each domain service re-fetches under its own
  row lock) — only the condition-evaluation snapshot is fixed per event.
- `stop_processing` on a rule that reached SUCCEEDED or PARTIALLY_SUCCEEDED
  prevents any lower-priority rule from running for this event at all.
- A rule that already produced a MATCHED/SUCCEEDED/PARTIALLY_SUCCEEDED
  AutomationExecution within the current correlation_id is never run again
  for that chain (SKIPPED_LOOP) — this is the "same-rule re-entry" policy.
"""
import time
import uuid
from dataclasses import dataclass

from django.db import models, transaction
from django.db.utils import IntegrityError
from django.utils import timezone

from .actions import ActionError, execute_action
from .conditions import ConditionContext, evaluate_condition
from .events import AutomationActionContext, MAX_AUTOMATION_DEPTH
from .models import AutomationRule, AutomationEvent, AutomationExecution, AutomationActionExecution

MAX_ACTIONS_PER_CORRELATION = 40


@dataclass
class ActionRunContext:
    execution_id: int
    rule_id: str
    correlation_id: uuid.UUID
    depth: int
    action_index: int


def _record_event_once(event):
    # The atomic() here is a savepoint, not a new top-level transaction: if
    # this insert collides on the event_id primary key (already processed),
    # only this savepoint rolls back — an enclosing transaction (if any,
    # e.g. a caller that hasn't gone through publish_event's on_commit
    # deferral) must not be left in Postgres's "aborted until rollback"
    # state by an uncaught-at-the-right-level IntegrityError.
    try:
        with transaction.atomic():
            AutomationEvent.objects.create(
                event_id=event.event_id, event_type=event.event_type, workspace_id=event.workspace_id,
                correlation_id=event.correlation_id, depth=event.depth,
            )
        return True
    except IntegrityError:
        return False


def _get_conversation(event):
    if not event.conversation_id:
        return None
    from conversations.models import Conversation
    return Conversation.objects.select_related(
        'workspace', 'visitor', 'assigned_to', 'team', 'queue', 'sla', 'sla__policy', 'sla__policy__calendar',
    ).filter(id=event.conversation_id).first()


def _create_execution(rule, event, conv, status, condition_result):
    return AutomationExecution.objects.create(
        workspace_id=event.workspace_id, rule=rule, rule_name_snapshot=rule.name if rule else '',
        trigger_type=event.event_type, event_id=event.event_id, correlation_id=event.correlation_id,
        depth=event.depth, conversation=conv, status=status, condition_result=condition_result,
        actor_type=event.actor_type, actor_id=event.actor_id or '',
    )


def process_event(event):
    """The single entry point for real (non-simulation) event processing.
    Simulation never calls this — see automations/simulation.py, which
    reuses evaluate_condition()/the field registry directly and never
    imports execute_action at all, so there is no code path by which a
    simulation request can reach a real mutation.
    """
    if event.depth > MAX_AUTOMATION_DEPTH:
        return

    if not _record_event_once(event):
        return  # already processed — idempotent no-op (test #39)

    actions_so_far = AutomationActionExecution.objects.filter(execution__correlation_id=event.correlation_id).count()
    if actions_so_far >= MAX_ACTIONS_PER_CORRELATION:
        return

    conv = _get_conversation(event)
    ctx = ConditionContext(event, conv)

    rules = AutomationRule.objects.filter(
        workspace_id=event.workspace_id, trigger_type=event.event_type, is_active=True,
    ).order_by('priority', 'created_at')

    now = timezone.now()
    for rule in rules:
        if rule.valid_from and rule.valid_from > now:
            continue
        if rule.valid_until and rule.valid_until < now:
            continue
        already_ran = AutomationExecution.objects.filter(
            rule=rule, correlation_id=event.correlation_id,
            status__in=[
                AutomationExecution.Status.MATCHED, AutomationExecution.Status.SUCCEEDED,
                AutomationExecution.Status.PARTIALLY_SUCCEEDED,
            ],
        ).exists()
        if already_ran:
            _create_execution(rule, event, conv, AutomationExecution.Status.SKIPPED_LOOP, None)
            continue
        if _run_rule(rule, event, conv, ctx):
            break  # stop_processing on a successful match


def _run_rule(rule, event, conv, ctx):
    start = time.monotonic()
    try:
        matched = evaluate_condition(rule.conditions or {}, ctx)
    except Exception as exc:
        execution = _create_execution(rule, event, conv, AutomationExecution.Status.FAILED, None)
        execution.error_summary = str(exc)[:500]
        execution.duration_ms = int((time.monotonic() - start) * 1000)
        execution.save(update_fields=['error_summary', 'duration_ms'])
        return False

    if not matched:
        _create_execution(rule, event, conv, AutomationExecution.Status.NOT_MATCHED, False)
        return False

    if conv is None or not (rule.actions or []):
        execution = _create_execution(rule, event, conv, AutomationExecution.Status.MATCHED, True)
        _finalize_rule_stats(rule)
        return False

    execution = _create_execution(rule, event, conv, AutomationExecution.Status.MATCHED, True)
    any_failed = False
    any_succeeded = False
    for i, action in enumerate(rule.actions or []):
        run_ctx = ActionRunContext(
            execution_id=execution.id, rule_id=str(rule.id), correlation_id=event.correlation_id,
            depth=event.depth, action_index=i,
        )
        action_type = action.get('type', '')
        try:
            with AutomationActionContext(event.correlation_id, event.depth):
                result, obj_type, obj_id = execute_action(conv, action, run_ctx)
            AutomationActionExecution.objects.create(
                execution=execution, action_index=i, action_type=action_type,
                status=AutomationActionExecution.Status.SUCCEEDED, result_summary=result,
                affected_object_type=obj_type, affected_object_id=obj_id,
            )
            any_succeeded = True
        except ActionError as exc:
            AutomationActionExecution.objects.create(
                execution=execution, action_index=i, action_type=action_type,
                status=AutomationActionExecution.Status.FAILED, error_summary=str(exc)[:500],
            )
            any_failed = True
        except Exception:
            AutomationActionExecution.objects.create(
                execution=execution, action_index=i, action_type=action_type,
                status=AutomationActionExecution.Status.FAILED, error_summary='Internal error while running this action.',
            )
            any_failed = True

    if any_failed and any_succeeded:
        final_status = AutomationExecution.Status.PARTIALLY_SUCCEEDED
    elif any_failed:
        final_status = AutomationExecution.Status.FAILED
    else:
        final_status = AutomationExecution.Status.SUCCEEDED

    execution.status = final_status
    execution.duration_ms = int((time.monotonic() - start) * 1000)
    execution.save(update_fields=['status', 'duration_ms'])
    _finalize_rule_stats(rule)

    return rule.stop_processing and final_status in (
        AutomationExecution.Status.SUCCEEDED, AutomationExecution.Status.PARTIALLY_SUCCEEDED,
    )


def _finalize_rule_stats(rule):
    AutomationRule.objects.filter(pk=rule.pk).update(
        last_executed_at=timezone.now(), execution_count=models.F('execution_count') + 1,
    )
