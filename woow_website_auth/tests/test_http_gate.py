# -*- coding: utf-8 -*-
"""前台閘門的 HTTP 行為（只用 website 本身的路由，不需要其他模組）

- 最長前綴優先（較窄、較嚴格的規則不會被 sequence 較前的寬規則遮蔽）
- 未知 auth_mode fail closed
- redirect_custom 的防迴圈：redirect_url='/' 不再讓所有請求都 403；
  導向目標被另一條規則擋下時回 403；導向目標是被擋 endpoint 的別名時也回 403
- 別名上的較窄規則不能放寬主路徑：/website/search 的 handler 同時註冊
  /website/search/page/<int:page>，兩條規則都要通過
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
        cls.silver_group = cls.env.ref('woow_website_auth.group_member_silver')
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

    def test_alias_only_rule_cannot_loosen_canonical_path(self):
        """/website/search（Silver）＋/website/search/page（signed_in）

        前一版把別名一起比最長前綴：/website/search/page 勝出，非 Silver 的 portal
        就能看 /website/search。現在兩條規則都要通過。
        """
        self._rule('/website/search', auth_mode='group', group_id=self.silver_group.id)
        self._rule('/website/search/page', sequence=50)
        self.authenticate('wauth_http_portal', 'wauth_http_portal')
        for url in ('/website/search', '/website/search?search=x', '/website/search/page/2'):
            with self.subTest(url=url):
                res = self._get(url)
                self.assertEqual(res.status_code, 303, url)
                self.assertEqual(self._location_path(res), '/website/access-denied')

        self.authenticate('wauth_http_gold', 'wauth_http_gold')  # Gold 隱含 Silver
        for url in ('/website/search', '/website/search?search=x', '/website/search/page/2'):
            with self.subTest(url=url):
                self.assertEqual(self._get(url).status_code, 200, url)

    def test_redirect_custom_to_alias_of_denied_endpoint_returns_403(self):
        """導向目標 /website/search 與被擋的 /website/search/page/N 是同一個 endpoint

        只看字面路徑會判斷「目標沒有規則」而導過去，接著目標又因別名被擋、再導向自己
        （無限迴圈）。現在導向目標也比對 endpoint 的別名 → 直接 403。
        """
        self._rule('/website/search/page', deny_action='redirect_custom',
                   redirect_url='/website/search')
        for url in ('/website/search/page/2', '/website/search'):
            with self.subTest(url=url):
                self.assertEqual(self._get(url).status_code, 403, url)
        # 已登入的使用者通過規則
        self.authenticate('wauth_http_portal', 'wauth_http_portal')
        self.assertEqual(self._get('/website/search/page/2').status_code, 200)
