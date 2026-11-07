# -*- coding: utf-8 -*-
"""比對邏輯單元測試（不需要 HTTP）

涵蓋：路由別名（endpoint.routing['routes']）、每條路徑各自最長前綴、
選出的規則全部都要通過（別名上的較窄規則不能放寬主路徑）、
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


def _ids(rules, path, routing_rule=None):
    """applicable_rules 選出的規則 id（依候選順序）"""
    return [r['id'] for r in gate.applicable_rules(rules, gate.candidate_paths(path, routing_rule))]


def _first(rules, path, routing_rule=None):
    ids = _ids(rules, path, routing_rule)
    return ids[0] if ids else None


@tagged('post_install', '-at_install', 'woow_website_auth')
class TestRuleMatching(TransactionCase):

    def test_route_static_prefix(self):
        self.assertEqual(gate.route_static_prefix('/event/page/<int:page>'), '/event/page')
        self.assertEqual(gate.route_static_prefix('/events'), '/events')
        self.assertEqual(gate.route_static_prefix('/<path:page>'), '/')
        self.assertEqual(gate.route_static_prefix('/'), '/')

    def test_alias_routes_are_candidates(self):
        """/events/page/2 命中的 endpoint 也註冊了 /event → /event 規則要套用"""
        routing = _routing_rule(EVENT_ROUTES, '/events/page/<int:page>')
        paths = gate.candidate_paths('/events/page/2', routing)
        self.assertIn('/event', paths)
        rules = [_rule(1, '/event')]
        self.assertEqual(_ids(rules, '/events/page/2', routing), [1])

    def test_alias_without_routing_rule_does_not_match(self):
        """沒有 routing rule 時（fallback／404）只看請求路徑本身，/events 不在 /event 之下"""
        rules = [_rule(1, '/event')]
        self.assertEqual(_ids(rules, '/events'), [])
        self.assertEqual(_ids(rules, '/eventx/1'), [])

    def test_boundary_and_normalization(self):
        rules = [_rule(1, '/app')]
        self.assertEqual(_ids(rules, '/application'), [])
        self.assertEqual(_first(rules, '/app'), 1)
        self.assertEqual(_first(rules, '/app/'), 1)
        self.assertEqual(_first(rules, '//app//x'), 1)

    def test_trailing_slash_prefix_from_legacy_data_matches(self):
        """舊資料 '/event/' 以前會比對成 '/event//' 永不命中；現在正規化後命中"""
        rules = [_rule(1, '/event/')]
        self.assertEqual(_first(rules, '/event/1'), 1)
        self.assertEqual(_first(rules, '/event'), 1)

    def test_legacy_root_prefix_only_matches_homepage(self):
        """舊資料 '/' 只匹配首頁與以轉換器開頭的路由（不會突然變成全站）"""
        rules = [_rule(1, '/')]
        self.assertEqual(_first(rules, '/'), 1)
        self.assertEqual(_ids(rules, '/shop'), [])
        # 路由以轉換器開頭的 endpoint（靜態部分是 '/'）也會被 '/' 規則涵蓋：較嚴格，不是全站
        self.assertEqual(_ids(rules, '/some-page', _routing_rule(['/<path:page>'])), [1])
        self.assertEqual(_ids(rules, '/shop', _routing_rule(['/shop', '/shop/page/<int:page>'])), [])

    def test_longest_prefix_wins_over_sequence(self):
        """較寬的 /event 排在前面（sequence 較小）時，較窄的 /event/vip 仍然勝出"""
        rules = [_rule(1, '/event'), _rule(2, '/event/vip', 'group', group_xml_id='base.group_system')]
        self.assertEqual(_first(rules, '/event/vip/x'), 2)
        self.assertEqual(_first(rules, '/event/other'), 1)

    def test_same_length_keeps_sequence_order(self):
        rules = [_rule(1, '/event'), _rule(2, '/event')]
        self.assertEqual(_first(rules, '/event'), 1)

    def test_unknown_auth_mode_fails_closed(self):
        IrHttp = type(self.env['ir.http'])
        admin = self.env.ref('base.user_admin')
        self.assertFalse(IrHttp._woow_rule_allows(_rule(1, '/x', 'bogus'), admin))
        self.assertFalse(IrHttp._woow_rule_allows(_rule(1, '/x', None), admin))
        self.assertTrue(IrHttp._woow_rule_allows(_rule(1, '/x', 'signed_in'), admin))

    def test_match_rule_single_path_longest_prefix(self):
        rules = [_rule(1, '/event'), _rule(2, '/event/page')]
        self.assertEqual(gate.match_rule(rules, '/event')['id'], 1)
        self.assertEqual(gate.match_rule(rules, '/event/page/2')['id'], 2)
        self.assertIsNone(gate.match_rule(rules, '/events'))

    def test_narrow_rule_on_alias_cannot_loosen_canonical_path(self):
        """/event（Silver）＋/event/page（signed_in）：/event 與 /events 都要套用 Silver

        前一版把所有別名一起丟進「最長前綴」，/event/page 勝出後 /event 只剩 signed_in。
        """
        silver = _rule(1, '/event', 'group', group_xml_id='woow_website_auth.group_member_silver')
        loose = _rule(2, '/event/page', 'signed_in')
        rules = [silver, loose]
        for path, route in (('/event', '/event'), ('/events', '/events'),
                            ('/events/page/2', '/events/page/<int:page>'),
                            ('/event/page/2', '/event/page/<int:page>')):
            with self.subTest(path=path):
                ids = _ids(rules, path, _routing_rule(EVENT_ROUTES, route))
                self.assertIn(1, ids)
                self.assertIn(2, ids)
        # 請求路徑本身選出的規則排第一（決定 deny_action）
        self.assertEqual(_first(rules, '/event', _routing_rule(EVENT_ROUTES, '/event')), 1)
        self.assertEqual(
            _first(rules, '/event/page/2', _routing_rule(EVENT_ROUTES, '/event/page/<int:page>')), 2)

    def test_alias_root_rule_cannot_loosen_canonical_path(self):
        """/event（Silver）＋/events（signed_in）：請求 /event 仍要套用 Silver"""
        rules = [_rule(1, '/event', 'group', group_xml_id='woow_website_auth.group_member_silver'),
                 _rule(2, '/events', 'signed_in')]
        self.assertEqual(_ids(rules, '/event', _routing_rule(EVENT_ROUTES, '/event')), [1, 2])
        self.assertEqual(_ids(rules, '/events', _routing_rule(EVENT_ROUTES, '/events')), [2, 1])

    def test_narrower_rule_still_loosens_paths_it_covers(self):
        """最長前綴仍然有效：endpoint 的所有路由都在 /shop/public 下時只套用 /shop/public"""
        routing = _routing_rule(['/shop/public', '/shop/public/<int:x>'], '/shop/public/<int:x>')
        rules = [_rule(1, '/shop', 'group', group_xml_id='base.group_system'),
                 _rule(2, '/shop/public', 'signed_in')]
        self.assertEqual(_ids(rules, '/shop/public/3', routing), [2])

    def test_all_chosen_rules_must_allow(self):
        """_woow_denying_rule 的判斷：任一選出的規則拒絕就拒絕"""
        IrHttp = type(self.env['ir.http'])
        portal = self.env['res.users'].create({
            'name': 'wauth unit portal', 'login': 'wauth_unit_portal',
            'groups_id': [(6, 0, [self.env.ref('base.group_portal').id])],
        })
        rules = [_rule(1, '/event', 'group', group_xml_id='woow_website_auth.group_member_silver'),
                 _rule(2, '/event/page', 'signed_in')]
        chosen = gate.applicable_rules(
            rules, gate.candidate_paths('/events', _routing_rule(EVENT_ROUTES, '/events')))
        denied = [r['id'] for r in chosen if not IrHttp._woow_rule_allows(r, portal)]
        self.assertEqual(denied, [1])
