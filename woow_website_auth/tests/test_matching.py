# -*- coding: utf-8 -*-
"""比對邏輯單元測試（不需要 HTTP）

涵蓋：路由別名（endpoint.routing['routes']）、最長前綴優先、
邊界比對、尾端斜線正規化、未知 auth_mode fail closed。
"""

from types import SimpleNamespace

from odoo.tests import TransactionCase, tagged

from odoo.addons.woow_website_auth.models import ir_http as gate


def _routing_rule(routes, rule=None):
    """模擬 werkzeug Rule：只需要 .rule 與 .endpoint.routing['routes']"""
    endpoint = SimpleNamespace(routing={'routes': list(routes)})
    return SimpleNamespace(rule=rule or routes[0], endpoint=endpoint)


def _rule(rule_id, prefix, auth_mode='signed_in', **kw):
    vals = {
        'id': rule_id,
        'path_prefix': prefix,
        'auth_mode': auth_mode,
        'deny_action': 'redirect_login',
        'redirect_url': '',
        'group_xml_id': False,
        'group_xml_ids': [],
    }
    vals.update(kw)
    return vals


EVENT_ROUTES = ['/event', '/event/page/<int:page>', '/events', '/events/page/<int:page>']


@tagged('post_install', '-at_install', 'woow_website_auth')
class TestRuleMatching(TransactionCase):

    def test_route_static_prefix(self):
        self.assertEqual(gate.route_static_prefix('/event/page/<int:page>'), '/event/page')
        self.assertEqual(gate.route_static_prefix('/events'), '/events')
        self.assertEqual(gate.route_static_prefix('/<path:page>'), '/')
        self.assertEqual(gate.route_static_prefix('/'), '/')

    def test_alias_routes_are_candidates(self):
        """/events/page/2 命中的 endpoint 也註冊了 /event → /event 規則要套用"""
        paths = gate.candidate_paths(
            '/events/page/2', _routing_rule(EVENT_ROUTES, '/events/page/<int:page>'))
        self.assertIn('/event', paths)
        rules = [_rule(1, '/event')]
        self.assertEqual(gate.match_rule(rules, paths)['id'], 1)

    def test_alias_without_routing_rule_does_not_match(self):
        """沒有 routing rule 時（fallback／404）只看請求路徑本身，/events 不在 /event 之下"""
        rules = [_rule(1, '/event')]
        self.assertIsNone(gate.match_rule(rules, gate.candidate_paths('/events')))
        self.assertIsNone(gate.match_rule(rules, gate.candidate_paths('/eventx/1')))

    def test_boundary_and_normalization(self):
        rules = [_rule(1, '/app')]
        self.assertIsNone(gate.match_rule(rules, gate.candidate_paths('/application')))
        self.assertEqual(gate.match_rule(rules, gate.candidate_paths('/app'))['id'], 1)
        self.assertEqual(gate.match_rule(rules, gate.candidate_paths('/app/'))['id'], 1)
        self.assertEqual(gate.match_rule(rules, gate.candidate_paths('//app//x'))['id'], 1)

    def test_trailing_slash_prefix_from_legacy_data_matches(self):
        """舊資料 '/event/' 以前會比對成 '/event//' 永不命中；現在正規化後命中"""
        rules = [_rule(1, '/event/')]
        self.assertEqual(gate.match_rule(rules, gate.candidate_paths('/event/1'))['id'], 1)
        self.assertEqual(gate.match_rule(rules, gate.candidate_paths('/event'))['id'], 1)

    def test_legacy_root_prefix_only_matches_homepage(self):
        """舊資料 '/' 維持只匹配首頁（不會突然變成全站）"""
        rules = [_rule(1, '/')]
        self.assertEqual(gate.match_rule(rules, gate.candidate_paths('/'))['id'], 1)
        self.assertIsNone(gate.match_rule(rules, gate.candidate_paths('/shop')))

    def test_longest_prefix_wins_over_sequence(self):
        """較寬的 /event 排在前面（sequence 較小）時，較窄的 /event/vip 仍然勝出"""
        rules = [_rule(1, '/event'), _rule(2, '/event/vip', 'group', group_xml_id='base.group_system')]
        self.assertEqual(gate.match_rule(rules, gate.candidate_paths('/event/vip/x'))['id'], 2)
        self.assertEqual(gate.match_rule(rules, gate.candidate_paths('/event/other'))['id'], 1)

    def test_same_length_keeps_sequence_order(self):
        rules = [_rule(1, '/event'), _rule(2, '/event')]
        self.assertEqual(gate.match_rule(rules, gate.candidate_paths('/event'))['id'], 1)

    def test_unknown_auth_mode_fails_closed(self):
        IrHttp = type(self.env['ir.http'])
        admin = self.env.ref('base.user_admin')
        self.assertFalse(IrHttp._woow_rule_allows(_rule(1, '/x', 'bogus'), admin))
        self.assertFalse(IrHttp._woow_rule_allows(_rule(1, '/x', None), admin))
        self.assertTrue(IrHttp._woow_rule_allows(_rule(1, '/x', 'signed_in'), admin))
