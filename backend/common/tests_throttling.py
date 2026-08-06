"""Regression tests proving the abuse-prone endpoints listed in the Phase 6
rate-limiting requirements actually throttle, not just that a `throttle_scope`
attribute exists on the view.

Throttling is globally disabled under `manage.py test` (settings.TESTING) so
that DRF's process-global cache-based counters don't cascade failures across
an unrelated 468-test suite run (see config/settings.py). These tests
deliberately monkeypatch `ScopedRateThrottle.THROTTLE_RATES` — the same
class attribute DRF itself populates from `REST_FRAMEWORK.DEFAULT_THROTTLE_RATES`
at import time — to re-enable a real, tight rate for just the scope under
test, proving the throttle_scope wiring on the view is genuinely load-bearing.
"""
from unittest.mock import patch

from django.core.cache import cache
from django.test import TransactionTestCase
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle

from accounts.models import User
from knowledge_base import services as kb_services
from knowledge_base.tests_base import KBTestMixin
from macros.models import Macro
from workspaces.models import WorkspaceMembership


class ThrottleTestMixin:
    def setUp(self):
        super().setUp()
        cache.clear()
        self.client = APIClient()

    def tearDown(self):
        cache.clear()
        super().tearDown()


class LoginThrottleTests(ThrottleTestMixin, KBTestMixin, TransactionTestCase):
    def test_login_endpoint_throttles_after_limit(self):
        ws = self.make_workspace()
        user = self.make_admin(ws, email='throttle-login@test.com')
        with patch.object(ScopedRateThrottle, 'THROTTLE_RATES', {'login': '2/min'}):
            for _ in range(2):
                res = self.client.post(
                    '/api/v1/auth/login/', {'email': user.email, 'password': 'pass1234'}, format='json',
                )
                self.assertEqual(res.status_code, 200)
            res = self.client.post(
                '/api/v1/auth/login/', {'email': user.email, 'password': 'pass1234'}, format='json',
            )
            self.assertEqual(res.status_code, 429)
            self.assertIn('Retry-After', res)


class WidgetStartThrottleTests(ThrottleTestMixin, KBTestMixin, TransactionTestCase):
    def test_widget_start_throttles_after_limit(self):
        ws = self.make_workspace()
        project = self.make_project(ws)
        visitor = self.make_visitor(project)
        session = self.make_visitor_session(visitor)
        with patch.object(ScopedRateThrottle, 'THROTTLE_RATES', {'widget_start': '1/min'}):
            res = self.client.post('/api/v1/widget/start/', {'session_token': str(session.token)}, format='json')
            self.assertEqual(res.status_code, 200)
            res = self.client.post('/api/v1/widget/start/', {'session_token': str(session.token)}, format='json')
            self.assertEqual(res.status_code, 429)


class KBSearchThrottleTests(ThrottleTestMixin, KBTestMixin, TransactionTestCase):
    def test_kb_public_search_throttles_after_limit(self):
        ws = self.make_workspace()
        project = self.make_project(ws)
        with patch.object(ScopedRateThrottle, 'THROTTLE_RATES', {'kb_search': '1/min'}):
            url = f'/api/v1/kb/public/articles/search/?project_key={project.public_key}&q=test'
            res = self.client.get(url)
            self.assertEqual(res.status_code, 200)
            res = self.client.get(url)
            self.assertEqual(res.status_code, 429)


class MacroExecutionThrottleTests(ThrottleTestMixin, KBTestMixin, TransactionTestCase):
    def test_macro_execution_throttles_after_limit(self):
        ws = self.make_workspace()
        operator = self.make_operator(ws, email='throttle-macro@test.com')
        macro = Macro.objects.create(
            workspace=ws, name='Throttle test macro', owner=operator,
            visibility=Macro.Visibility.WORKSPACE, is_active=True,
            actions=[{'type': 'ADD_TAG', 'params': {'tag': 'x'}}],
        )
        project = self.make_project(ws)
        visitor = self.make_visitor(project)
        conv = self.make_conversation(ws, project, visitor)

        login_res = self.client.post(
            '/api/v1/auth/login/', {'email': operator.email, 'password': 'pass1234'}, format='json',
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login_res.data['access']}")

        with patch.object(ScopedRateThrottle, 'THROTTLE_RATES', {'macro_execution': '1/min'}):
            url = f'/api/v1/macros/{macro.id}/execute/'
            res = self.client.post(url, {'conversation_id': str(conv.id), 'idempotency_key': 'k1'}, format='json')
            self.assertEqual(res.status_code, 200)
            res = self.client.post(url, {'conversation_id': str(conv.id), 'idempotency_key': 'k2'}, format='json')
            self.assertEqual(res.status_code, 429)
