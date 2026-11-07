# -*- coding: utf-8 -*-
"""path_prefix 正規化與驗證"""

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'woow_website_auth')
class TestPathPrefixValidation(TransactionCase):

    def _create(self, prefix, **kw):
        vals = {
            'name': 'rule %s' % prefix,
            'page_type': 'dynamic',
            'path_prefix': prefix,
            'auth_mode': 'signed_in',
            'deny_action': 'redirect_login',
        }
        vals.update(kw)
        return self.env['woow.website.auth.rule'].create(vals)

    def test_trailing_slash_is_stripped_on_create_and_write(self):
        rule = self._create('/event/')
        self.assertEqual(rule.path_prefix, '/event')
        rule.write({'path_prefix': ' /members// '})
        self.assertEqual(rule.path_prefix, '/members')

    def test_trailing_slash_rule_is_used_by_cache(self):
        rule = self._create('/vip/')
        rules = self.env['woow.website.auth.rule']._get_active_rules(0)
        self.assertIn('/vip', [r['path_prefix'] for r in rules if r['id'] == rule.id])

    def test_root_prefix_rejected(self):
        for prefix in ('/', '//', ' / '):
            with self.subTest(prefix=prefix), self.assertRaises(ValidationError):
                self._create(prefix)

    def test_query_fragment_whitespace_rejected(self):
        for prefix in ('/event?x=1', '/event#top', '/my event', '/event\t1'):
            with self.subTest(prefix=prefix), self.assertRaises(ValidationError):
                self._create(prefix)

    def test_empty_segment_rejected(self):
        with self.assertRaises(ValidationError):
            self._create('/a//b')

    def test_must_start_with_slash(self):
        with self.assertRaises(ValidationError):
            self._create('event')

    def test_prefix_under_bypass_rejected(self):
        for prefix in ('/web', '/web/foo', '/sitemap.xml', '/website/access-denied'):
            with self.subTest(prefix=prefix), self.assertRaises(ValidationError):
                self._create(prefix)

    def test_valid_prefixes_accepted(self):
        for prefix in ('/event', '/shop/premium', '/website', '/my/orders'):
            with self.subTest(prefix=prefix):
                self.assertEqual(self._create(prefix).path_prefix, prefix)

    def test_write_invalid_prefix_rejected(self):
        rule = self._create('/event')
        with self.assertRaises(ValidationError):
            rule.write({'path_prefix': '/'})
