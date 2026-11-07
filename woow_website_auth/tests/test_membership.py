# -*- coding: utf-8 -*-
"""會員升級／降級 action 的呼叫者權限"""

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged

MANAGER = 'woow_website_auth.group_membership_manager'
ACTIONS = ('action_upgrade_to_silver', 'action_upgrade_to_gold', 'action_downgrade_to_portal')


@tagged('post_install', '-at_install', 'woow_website_auth')
class TestMembershipManager(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.silver = cls.env.ref('woow_website_auth.group_member_silver')
        cls.gold = cls.env.ref('woow_website_auth.group_member_gold')
        cls.employee = new_test_user(cls.env, 'wauth_employee', groups='base.group_user')
        cls.erp_manager = new_test_user(
            cls.env, 'wauth_erp_manager', groups='base.group_user,base.group_erp_manager')
        cls.target = new_test_user(cls.env, 'wauth_target', groups='base.group_portal')
        cls.other_portal = new_test_user(cls.env, 'wauth_portal_caller', groups='base.group_portal')

    def _groups(self):
        return set(self.target.sudo().groups_id.ids)

    def test_employee_without_group_cannot_change_membership(self):
        """只有 base.group_user 的員工：三個 action 都 AccessError，groups_id 不變"""
        partner = self.target.partner_id.with_user(self.employee)
        self.target.write({'groups_id': [(4, self.silver.id)]})  # 讓降級也有東西可以拿掉
        before = self._groups()
        for action in ACTIONS:
            with self.subTest(action=action), self.assertRaises(AccessError):
                getattr(partner, action)()
            self.assertEqual(self._groups(), before)

    def test_portal_caller_cannot_change_membership(self):
        partner = self.target.partner_id.with_user(self.other_portal)
        for action in ACTIONS:
            with self.subTest(action=action), self.assertRaises(AccessError):
                getattr(partner, action)()

    def test_erp_manager_implies_membership_manager(self):
        self.assertTrue(self.erp_manager.has_group(MANAGER))
        partner = self.target.partner_id.with_user(self.erp_manager)
        partner.action_upgrade_to_silver()
        self.assertIn(self.silver, self.target.sudo().groups_id)
        partner.action_upgrade_to_gold()
        self.assertIn(self.gold, self.target.sudo().groups_id)
        partner.action_downgrade_to_portal()
        self.assertNotIn(self.gold, self.target.sudo().groups_id)
        self.assertNotIn(self.silver, self.target.sudo().groups_id)
        self.assertIn(self.env.ref('base.group_portal'), self.target.sudo().groups_id)

    def test_bot_account_in_manager_group_succeeds(self):
        """API／AI bot：一般內部使用者加入 group_membership_manager 後可以呼叫"""
        bot = new_test_user(self.env, 'wauth_bot', groups='base.group_user,%s' % MANAGER)
        self.assertFalse(bot.has_group('base.group_erp_manager'))
        self.target.partner_id.with_user(bot).action_upgrade_to_gold()
        self.assertIn(self.gold, self.target.sudo().groups_id)

    def test_admin_is_membership_manager(self):
        admin = self.env.ref('base.user_admin')
        self.assertIn(self.env.ref(MANAGER), admin.groups_id)
        self.assertTrue(admin.has_group(MANAGER))

    def test_manager_group_cannot_be_given_to_portal_user(self):
        """群組隱含 base.group_user，portal 使用者不能被加入（使用者類型互斥）"""
        manager_group = self.env.ref(MANAGER)
        self.assertIn(self.env.ref('base.group_user'), manager_group.implied_ids)
        with self.assertRaises(Exception):
            with self.env.cr.savepoint():
                self.other_portal.write({'groups_id': [(4, manager_group.id)]})
