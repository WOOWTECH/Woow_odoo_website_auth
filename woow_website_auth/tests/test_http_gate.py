# -*- coding: utf-8 -*-
"""前台閘門的 HTTP 行為（只用 website 本身的路由，不需要其他模組）

- 最長前綴優先（較窄、較嚴格的規則不會被 sequence 較前的寬規則遮蔽）
- 未知 auth_mode fail closed
- redirect_custom 的防迴圈：redirect_url='/' 不再讓所有請求都 403；
  導向目標被另一條規則擋下時回 403
"""

from urllib.parse import urlsplit

from odoo.tests import HttpCase, new_test_user, tagged


@tagged('post_install', '-at_install', 'woow_website_auth')
class TestHttpGate(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Rule = cls.env['woow.website.auth.rule']
        cls.Rule.search([]).write({'active': False})
        cls.portal = new_test_user(cls.env, 'wauth_http_portal', groups='base.group_portal')
        cls.gold = new_test_user(
            cls.env, 'wauth_http_gold', groups='base.group_portal,woow_website_auth.group_member_gold')

    def _rule(self, prefix, **kw):
        vals = {
            'name': 'test %s' % prefix,
            'page_type': 'dynamic',
            'path_prefix': prefix,
            'auth_mode': 'signed_in',
            'deny_action': 'redirect_login',
        }
        vals.update(kw)
        return self.Rule.create(vals)

    def _get(self, url):
        return self.url_open(url, allow_redirects=False)

    def _location_path(self, res):
        return urlsplit(res.headers.get('Location', '')).path

    def test_longest_prefix_wins_over_sequence(self):
        """寬規則 /website（signed_in，sequence 1）不能遮蔽窄規則 /website/info（Gold，sequence 50）"""
        self._rule('/website', sequence=1)
        self._rule('/website/info', sequence=50, auth_mode='group',
                   group_id=self.env.ref('woow_website_auth.group_member_gold').id)
        self.authenticate('wauth_http_portal', 'wauth_http_portal')
        res = self._get('/website/info')
        self.assertEqual(res.status_code, 303)
        self.assertEqual(self._location_path(res), '/website/access-denied')

        self.authenticate('wauth_http_gold', 'wauth_http_gold')
        self.assertEqual(self._get('/website/info').status_code, 200)

    def test_unknown_auth_mode_fails_closed(self):
        rule = self._rule('/website/info')
        self.env.cr.execute(
            "UPDATE woow_website_auth_rule SET auth_mode = 'bogus' WHERE id = %s", (rule.id,))
        self.env.invalidate_all()
        self.env.registry.clear_cache()
        self.authenticate('wauth_http_portal', 'wauth_http_portal')
        res = self._get('/website/info')
        self.assertEqual(res.status_code, 303)
        self.assertEqual(self._location_path(res), '/website/access-denied')

    def test_redirect_custom_to_root_redirects(self):
        """redirect_url='/'：舊版因 path.startswith('/') 對所有路徑回 403"""
        self._rule('/website/info', deny_action='redirect_custom', redirect_url='/')
        res = self._get('/website/info')
        self.assertEqual(res.status_code, 303)
        self.assertEqual(self._location_path(res), '/')

    def test_redirect_custom_cross_rule_loop_returns_403(self):
        """A 導向 B、B 又擋同一個使用者 → 直接 403，不在兩條規則間來回導向"""
        self._rule('/website/info', deny_action='redirect_custom', redirect_url='/members-only?x=1')
        self._rule('/members-only', deny_action='redirect_login')
        res = self._get('/website/info')
        self.assertEqual(res.status_code, 403)

    def test_redirect_custom_target_allowed_redirects(self):
        """導向目標對該使用者是允許的 → 正常導向"""
        self._rule('/website/info', auth_mode='group', deny_action='redirect_custom',
                   group_id=self.env.ref('woow_website_auth.group_member_gold').id,
                   redirect_url='/members-area/upgrade')
        self._rule('/members-area')  # signed_in
        self.authenticate('wauth_http_portal', 'wauth_http_portal')
        res = self._get('/website/info')
        self.assertEqual(res.status_code, 303)
        self.assertEqual(self._location_path(res), '/members-area/upgrade')
