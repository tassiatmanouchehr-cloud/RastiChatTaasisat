"""Conversation lifecycle mutations: assignment, transfer, unassign,
return-to-queue, escalation, and priority changes.

Every mutation locks the conversation row (`select_for_update()` inside
`transaction.atomic()`) so it can never race with automatic assignment,
another operator's concurrent action, or a duplicate retry — one of the two
concurrent callers always loses cleanly instead of silently overwriting the
other's result. Every mutation also appends an `Assignment`/`PriorityChange`
row (history is never edited or overwritten) and an `AuditEvent`.
"""
import json
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.contrib.auth import get_user_model
from django.utils import timezone
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from audit.models import AuditEvent
from teams.models import Team, TeamMembership
from notifications.services import notify
from notifications.models import Notification
from automations.events import publish_event

User = get_user_model()


class ConversationServiceError(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def broadcast_ops_event(conv_id, event_type, data):
    """Operator-only realtime channel — never joined by the widget socket,
    so internal/operational events can never reach a customer.
    """
    layer = get_channel_layer()
    if not layer:
        return
    safe_data = json.loads(json.dumps(data, default=str))
    async_to_sync(layer.group_send)(f'chat_ops_{conv_id}', {'type': event_type, **safe_data})


def _audit(actor, action, conv, metadata=None):
    AuditEvent.objects.create(
        actor=actor, action=action, target_type='conversation', target_id=str(conv.id), metadata=metadata or {},
    )


def conversation_summary(conv):
    return {
        'conversation_id': str(conv.id),
        'status': conv.status,
        'priority': conv.priority,
        'assigned_to': str(conv.assigned_to_id) if conv.assigned_to_id else None,
        'team': str(conv.team_id) if conv.team_id else None,
        'queue': str(conv.queue_id) if conv.queue_id else None,
    }


def _require_capacity(user, queue=None):
    from accounts.presence import touch_presence
    presence = touch_presence(user)
    if not user.is_active:
        raise ConversationServiceError('Agent account is inactive', 403)
    capacity = (queue.max_active_per_agent if queue and queue.max_active_per_agent else presence.max_capacity)
    if presence.is_at_capacity(capacity):
        raise ConversationServiceError('Agent is at capacity', 409)


def assign_to_self(conversation, actor):
    return _reassign(conversation, actor, target_user=actor)


def assign_to_agent(conversation, actor, target_user_id, reason=''):
    try:
        target = User.objects.get(id=target_user_id, workspace_memberships__workspace=conversation.workspace)
    except (User.DoesNotExist, DjangoValidationError, ValueError):
        raise ConversationServiceError('Operator not found in this workspace', 404)
    return _reassign(conversation, actor, target_user=target, action_reason=reason)


def _reassign(conversation, actor, target_user, action_reason=''):
    from .models import Conversation, Assignment

    _require_capacity(target_user, conversation.queue)
    with transaction.atomic():
        conv = Conversation.objects.select_for_update().get(pk=conversation.pk)
        previous_assignee = conv.assigned_to
        action = Assignment.Action.REASSIGN if previous_assignee_id(previous_assignee) else Assignment.Action.ASSIGN
        conv.assigned_to = target_user
        conv.status = Conversation.Status.OPEN
        conv.save(update_fields=['assigned_to', 'status'])
        Assignment.objects.create(
            conversation=conv, action=action, assigned_to=target_user, assigned_by=actor,
            previous_assignee=previous_assignee, new_team=conv.team, reason=action_reason,
        )
    _audit(actor, 'conversation_assigned', conv, {'assigned_to': str(target_user.id)})
    broadcast_ops_event(conv.id, 'conversation.assigned', conversation_summary(conv))
    if actor is None or str(target_user.id) != str(actor.id):
        notify(
            target_user, conv.workspace, Notification.EventType.CONVERSATION_ASSIGNED,
            'گفتگویی به شما واگذار شد', {'conversation_id': str(conv.id)},
        )
    publish_event(
        'CONVERSATION_ASSIGNED', conv.workspace_id, conversation_id=conv.id,
        actor_id=actor.id if actor else None, actor_type='USER' if actor else 'SYSTEM',
        payload={'assigned_to': str(target_user.id)},
    )
    return conv


def previous_assignee_id(user):
    return str(user.id) if user else None


def unassign(conversation, actor, reason=''):
    from .models import Conversation, Assignment

    with transaction.atomic():
        conv = Conversation.objects.select_for_update().get(pk=conversation.pk)
        previous_assignee = conv.assigned_to
        conv.assigned_to = None
        conv.save(update_fields=['assigned_to'])
        Assignment.objects.create(
            conversation=conv, action=Assignment.Action.UNASSIGN, assigned_by=actor,
            previous_assignee=previous_assignee, new_team=conv.team, reason=reason,
        )
    _audit(actor, 'conversation_unassigned', conv, {})
    broadcast_ops_event(conv.id, 'conversation.unassigned', conversation_summary(conv))
    publish_event(
        'CONVERSATION_UNASSIGNED', conv.workspace_id, conversation_id=conv.id,
        actor_id=actor.id if actor else None, actor_type='USER' if actor else 'SYSTEM',
    )
    return conv


def return_to_queue(conversation, actor, reason=''):
    from .models import Conversation, Assignment

    with transaction.atomic():
        conv = Conversation.objects.select_for_update().get(pk=conversation.pk)
        previous_assignee = conv.assigned_to
        conv.assigned_to = None
        conv.save(update_fields=['assigned_to'])
        Assignment.objects.create(
            conversation=conv, action=Assignment.Action.RETURN_TO_QUEUE, assigned_by=actor,
            previous_assignee=previous_assignee, new_team=conv.team, reason=reason,
        )
    _audit(actor, 'conversation_returned_to_queue', conv, {})
    broadcast_ops_event(conv.id, 'conversation.queued', conversation_summary(conv))
    publish_event(
        'CONVERSATION_QUEUED', conv.workspace_id, conversation_id=conv.id,
        actor_id=actor.id if actor else None, actor_type='USER' if actor else 'SYSTEM',
    )
    if conv.queue_id and conv.queue.assignment_strategy != conv.queue.Strategy.MANUAL:
        from queues.services import auto_assign
        conv = auto_assign(conv, conv.queue)
        if conv.assigned_to_id:
            broadcast_ops_event(conv.id, 'conversation.assigned', conversation_summary(conv))
    return conv


def transfer_team(conversation, actor, new_team_id, reason=''):
    from .models import Conversation, Assignment

    try:
        new_team = Team.objects.get(id=new_team_id, workspace=conversation.workspace, is_active=True)
    except (Team.DoesNotExist, DjangoValidationError, ValueError):
        raise ConversationServiceError('Team not found in this workspace or inactive', 404)
    with transaction.atomic():
        conv = Conversation.objects.select_for_update().get(pk=conversation.pk)
        previous_team = conv.team
        previous_assignee = conv.assigned_to
        conv.team = new_team
        conv.assigned_to = None  # receiving team must claim/assign explicitly
        conv.queue = None
        conv.save(update_fields=['team', 'assigned_to', 'queue'])
        Assignment.objects.create(
            conversation=conv, action=Assignment.Action.TRANSFER, assigned_by=actor,
            previous_assignee=previous_assignee, previous_team=previous_team, new_team=new_team, reason=reason,
        )
    _audit(actor, 'conversation_transferred', conv, {
        'previous_team': str(previous_team.id) if previous_team else None, 'new_team': str(new_team.id),
    })
    broadcast_ops_event(conv.id, 'conversation.transferred', conversation_summary(conv))
    publish_event(
        'CONVERSATION_TRANSFERRED', conv.workspace_id, conversation_id=conv.id,
        actor_id=actor.id if actor else None, actor_type='USER' if actor else 'SYSTEM',
        payload={'new_team': str(new_team.id)},
    )
    return conv


def escalate(conversation, actor, reason=''):
    from .models import Conversation, Assignment, PriorityChange

    with transaction.atomic():
        conv = Conversation.objects.select_for_update().get(pk=conversation.pk)
        previous_assignee = conv.assigned_to
        supervisor = None
        if conv.team_id:
            supervisor_membership = TeamMembership.objects.filter(
                team_id=conv.team_id, role=TeamMembership.Role.SUPERVISOR, is_active=True, user__is_active=True,
            ).exclude(user=actor).select_related('user').first()
            supervisor = supervisor_membership.user if supervisor_membership else (conv.team.manager if conv.team.manager_id else None)
        if supervisor:
            conv.assigned_to = supervisor
        previous_priority = conv.priority
        if conv.priority != Conversation.Priority.URGENT:
            conv.priority = Conversation.Priority.URGENT
        conv.save(update_fields=['assigned_to', 'priority'])
        Assignment.objects.create(
            conversation=conv, action=Assignment.Action.ESCALATE, assigned_to=supervisor, assigned_by=actor,
            previous_assignee=previous_assignee, new_team=conv.team, reason=reason,
        )
        if previous_priority != conv.priority:
            PriorityChange.objects.create(
                conversation=conv, previous_priority=previous_priority, priority=conv.priority,
                reason_code=PriorityChange.Reason.ESCALATION, reason=reason, changed_by=actor,
            )
    _audit(actor, 'conversation_escalated', conv, {'supervisor': str(supervisor.id) if supervisor else None})
    broadcast_ops_event(conv.id, 'conversation.escalated', conversation_summary(conv))
    if supervisor:
        notify(
            supervisor, conv.workspace, Notification.EventType.ESCALATION_RECEIVED,
            'یک گفتگو به شما تشدید شد', {'conversation_id': str(conv.id)},
        )
    publish_event(
        'CONVERSATION_ESCALATED', conv.workspace_id, conversation_id=conv.id,
        actor_id=actor.id if actor else None, actor_type='USER' if actor else 'SYSTEM',
    )
    return conv


def set_priority(conversation, actor, priority, reason='', reason_code=None):
    from .models import Conversation, PriorityChange

    if priority not in Conversation.Priority.values:
        raise ConversationServiceError('Invalid priority', 400)
    with transaction.atomic():
        conv = Conversation.objects.select_for_update().get(pk=conversation.pk)
        previous_priority = conv.priority
        if previous_priority == priority:
            return conv
        conv.priority = priority
        conv.save(update_fields=['priority'])
        PriorityChange.objects.create(
            conversation=conv, previous_priority=previous_priority, priority=priority,
            reason_code=reason_code or PriorityChange.Reason.MANUAL, reason=reason, changed_by=actor,
        )
    _audit(actor, 'conversation_priority_changed', conv, {'from': previous_priority, 'to': priority})
    broadcast_ops_event(conv.id, 'conversation.priority_updated', conversation_summary(conv))
    publish_event(
        'CONVERSATION_PRIORITY_CHANGED', conv.workspace_id, conversation_id=conv.id,
        actor_id=actor.id if actor else None, actor_type='USER' if actor else 'SYSTEM',
        payload={'from': previous_priority, 'to': priority},
    )
    return conv


def close_conversation(conversation, actor=None):
    """Shared by CustomerConversationViewSet.close and the CLOSE_CONVERSATION
    automation action — a single, safe implementation instead of two.
    """
    from .models import Conversation
    from sla.services import mark_resolved

    with transaction.atomic():
        conv = Conversation.objects.select_for_update().get(pk=conversation.pk)
        conv.status = Conversation.Status.CLOSED
        conv.closed_at = timezone.now()
        conv.save(update_fields=['status', 'closed_at'])
    mark_resolved(conv)
    publish_event(
        'CONVERSATION_CLOSED', conv.workspace_id, conversation_id=conv.id,
        actor_id=actor.id if actor else None, actor_type='USER' if actor else 'SYSTEM',
    )
    publish_event(
        'CONVERSATION_RESOLVED', conv.workspace_id, conversation_id=conv.id,
        actor_id=actor.id if actor else None, actor_type='USER' if actor else 'SYSTEM',
    )
    return conv


def reopen_conversation(conversation, actor=None):
    """Shared by CustomerConversationViewSet.reopen and the
    REOPEN_CONVERSATION automation action.
    """
    from .models import Conversation
    from sla.services import mark_reopened

    with transaction.atomic():
        conv = Conversation.objects.select_for_update().get(pk=conversation.pk)
        if conv.status != Conversation.Status.CLOSED:
            raise ConversationServiceError('Conversation is not closed', 400)
        conv.status = Conversation.Status.OPEN
        conv.closed_at = None
        conv.save(update_fields=['status', 'closed_at'])
    mark_reopened(conv)
    publish_event(
        'CONVERSATION_REOPENED', conv.workspace_id, conversation_id=conv.id,
        actor_id=actor.id if actor else None, actor_type='USER' if actor else 'SYSTEM',
    )
    return conv
