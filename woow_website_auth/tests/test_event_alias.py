# -*- coding: utf-8 -*-
"""路由別名：/event 規則必須同時擋住 /events、/events/page/N（finding 77785ac194d4）

website_event 的 events() 以 ['/event', '/event/page/<int:page>', '/events',
'/events/page/<int:page>'] 註冊同一個 handler。需要 website_event 已安裝
（不是本模組的依賴；沒裝時略過）。
"""

import logging
import unittest
from urllib.parse import parse_qs, urlsplit

from odoo.tests import HttpCase, new_test_user, tagged

_logger = logging.getLogger(__name__)

EVENT_URLS = ('/event', '/events', '/events/page/2', '/events?search=x', '/event/page/2')


@tagged('post_install', '-at_install', 'woow_website_auth')
class TestEventAliasGate(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not cls.env['ir.module.module'].search_count(
                [('name', '=', 'website_event'), ('state', '=', 'installed')]):
            _logger.warning(
                'woow_website_auth: website_event is not installed, %s SKIPPED '
                '(HTTP regression for 77785ac194d4 not exercised; the same logic is '
                'covered by test_matching and test_http_gate)', cls.__name__)
            raise unittest.SkipTest('website_event is not installed')
        Rule = cls.env['woow.website.auth.rule']
        Rule.search([]).write({'active': False})
        Rule.create({
            'name': 'event members only',
            'page_type': 'dynamic',
            'path_prefix': '/event',
            'auth_mode': 'multi_group',
            'group_ids': [(6, 0, [
                cls.env.ref('woow_website_auth.group_member_silver').id,
                cls.env.ref('base.group_user').id,
            ])],
            'deny_action': 'redirect_login',
        })
        cls.portal = new_test_user(cls.env, 'wauth_ev_portal', groups='base.group_portal')
        cls.silver = new_test_user(
            cls.env, 'wauth_ev_silver',
            groups='base.group_portal,woow_website_auth.group_member_silver')
        cls.internal = new_test_user(cls.env, 'wauth_ev_internal', groups='base.group_user')

    def _get(self, url):
        return self.url_open(url, allow_redirects=False)

    def test_public_redirected_to_login(self):
        for url in EVENT_URLS:
            with self.subTest(url=url):
                res = self._get(url)
                self.assertEqual(res.status_code, 303, url)
                loc = urlsplit(res.headers['Location'])
                self.assertEqual(loc.path, '/web/login')
                self.assertEqual(parse_qs(loc.query).get('redirect'), [urlsplit(url).path])

    def test_portal_without_silver_denied(self):
        self.authenticate('wauth_ev_portal', 'wauth_ev_portal')
        for url in EVENT_URLS:
            with self.subTest(url=url):
                res = self._get(url)
                self.assertEqual(res.status_code, 303, url)
                self.assertEqual(urlsplit(res.headers['Location']).path, '/website/access-denied')

    def test_silver_member_allowed(self):
        self.authenticate('wauth_ev_silver', 'wauth_ev_silver')
        for url in EVENT_URLS:
            with self.subTest(url=url):
                self.assertEqual(self._get(url).status_code, 200, url)

    def test_internal_user_allowed(self):
        self.authenticate('wauth_ev_internal', 'wauth_ev_internal')
        for url in EVENT_URLS:
            with self.subTest(url=url):
                self.assertEqual(self._get(url).status_code, 200, url)


@tagged('post_install', '-at_install', 'woow_website_auth')
class TestEventAliasNestedRules(HttpCase):
    """別名上的較窄／較寬規則不能放寬主路徑（第 2 輪審查的阻擋項）"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not cls.env['ir.module.module'].search_count(
                [('name', '=', 'website_event'), ('state', '=', 'installed')]):
            _logger.warning(
                'woow_website_auth: website_event is not installed, %s SKIPPED', cls.__name__)
            raise unittest.SkipTest('website_event is not installed')
        cls.Rule = cls.env['woow.website.auth.rule']
        cls.Rule.search([]).write({'active': False})
        cls.silver_group = cls.env.ref('woow_website_auth.group_member_silver')
        cls.portal = new_test_user(cls.env, 'wauth_nest_portal', groups='base.group_portal')
        cls.silver = new_test_user(
            cls.env, 'wauth_nest_silver',
            groups='base.group_portal,woow_website_auth.group_member_silver')

    def _rule(self, prefix, **kw):
        vals = {
            'name': 'nested %s' % prefix,
            'page_type': 'dynamic',
            'path_prefix': prefix,
            'auth_mode': 'signed_in',
            'deny_action': 'redirect_login',
        }
        vals.update(kw)
        return self.Rule.create(vals)

    def _get(self, url):
        return self.url_open(url, allow_redirects=False)

    def _assert_portal_denied_silver_allowed(self, urls):
        self.authenticate('wauth_nest_portal', 'wauth_nest_portal')
        for url in urls:
            with self.subTest(user='portal', url=url):
                res = self._get(url)
                self.assertEqual(res.status_code, 303, url)
                self.assertEqual(urlsplit(res.headers['Location']).path, '/website/access-denied')
        self.authenticate('wauth_nest_silver', 'wauth_nest_silver')
        for url in urls:
            with self.subTest(user='silver', url=url):
                self.assertEqual(self._get(url).status_code, 200, url)

    def test_event_silver_plus_event_page_signed_in(self):
        """/event（Silver）＋/event/page（signed_in）：/event 與 /events 都要 Silver"""
        self._rule('/event', auth_mode='group', group_id=self.silver_group.id)
        self._rule('/event/page', sequence=50)
        self._assert_portal_denied_silver_allowed(
            ('/event', '/events', '/events/page/2', '/event/page/2', '/events?search=x'))

    def test_event_silver_plus_events_signed_in(self):
        """/event（Silver）＋/events（signed_in）：/event 仍要 Silver（/events 是同一個 endpoint）"""
        self._rule('/event', auth_mode='group', group_id=self.silver_group.id)
        self._rule('/events', sequence=50)
        self._assert_portal_denied_silver_allowed(('/event', '/event/page/2', '/events'))

    def test_redirect_custom_to_alias_returns_403(self):
        """/event 規則導向 /events（同一個 endpoint）→ 會無限導向，直接 403"""
        self._rule('/event', deny_action='redirect_custom', redirect_url='/events')
        for url in ('/event', '/events'):
            with self.subTest(url=url):
                self.assertEqual(self._get(url).status_code, 403, url)
