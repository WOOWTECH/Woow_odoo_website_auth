# -*- coding: utf-8 -*-
"""路由別名：/event 規則必須同時擋住 /events、/events/page/N（finding 77785ac194d4）

website_event 的 events() 以 ['/event', '/event/page/<int:page>', '/events',
'/events/page/<int:page>'] 註冊同一個 handler。需要 website_event 已安裝
（不是本模組的依賴；沒裝時略過）。
"""

import unittest
from urllib.parse import parse_qs, urlsplit

from odoo.tests import HttpCase, new_test_user, tagged

EVENT_URLS = ('/event', '/events', '/events/page/2', '/events?search=x', '/event/page/2')


@tagged('post_install', '-at_install', 'woow_website_auth')
class TestEventAliasGate(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not cls.env['ir.module.module'].search_count(
                [('name', '=', 'website_event'), ('state', '=', 'installed')]):
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
