# -*- coding: utf-8 -*-
"""會員升級/降級 Public API

在 res.partner 上提供會員等級操作方法，
供外部系統（含 AI/LLM）透過 JSON-RPC call_kw 呼叫。

18.0.1.3.1 起只有「會員等級管理員」群組
（woow_website_auth.group_membership_manager）的成員可以呼叫。
base.group_erp_manager（Access Rights 管理員，含 Settings／系統管理員）
自動隱含此群組，base.user_admin 也會直接被加入。
只有 base.group_user 的一般內部使用者、API／AI bot 帳號
必須另外加入此群組，否則會得到 AccessError。
"""

from odoo import _, models
from odoo.exceptions import AccessError

MEMBERSHIP_MANAGER_GROUP = 'woow_website_auth.group_membership_manager'


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def _check_membership_manager(self):
        """檢查當前用戶是否為會員等級管理員

        寫入 res.users.groups_id 在 core 只開放給 base.group_erp_manager，
        這些 action 以 sudo() 寫入，因此先在這裡限制呼叫者：
        必須屬於 woow_website_auth.group_membership_manager
        （由 base.group_erp_manager 隱含；API／AI bot 帳號要另外加入）。

        :raises AccessError: 呼叫者不在會員等級管理員群組時拋出
        """
        if not self.env.user.has_group(MEMBERSHIP_MANAGER_GROUP):
            raise AccessError(
                _('Only membership managers can modify membership levels.')
            )

    def _get_membership_groups(self):
        """取得所有會員等級 group 的 recordset

        :return: res.groups recordset
        """
        return (
            self.env.ref('woow_website_auth.group_member_silver')
            | self.env.ref('woow_website_auth.group_member_gold')
        )

    def action_upgrade_to_silver(self):
        """將 partner 對應的用戶升級為 Silver 會員

        加入 Silver group。
        若 partner 沒有關聯的用戶，則不做任何操作。
        僅限會員等級管理員呼叫。

        :raises AccessError: 呼叫者不是會員等級管理員時拋出
        """
        self._check_membership_manager()
        silver_group = self.env.ref('woow_website_auth.group_member_silver')
        for partner in self:
            users = partner.user_ids
            if not users:
                continue
            users.sudo().write({
                'groups_id': [(4, silver_group.id)],
            })

    def action_upgrade_to_gold(self):
        """將 partner 對應的用戶升級為 Gold 會員

        加入 Gold group。透過 implied_ids 鏈式繼承，
        Gold 自動包含 Silver 和 Portal 權限。
        僅限會員等級管理員呼叫。

        :raises AccessError: 呼叫者不是會員等級管理員時拋出
        """
        self._check_membership_manager()
        gold_group = self.env.ref('woow_website_auth.group_member_gold')
        for partner in self:
            users = partner.user_ids
            if not users:
                continue
            users.sudo().write({
                'groups_id': [(4, gold_group.id)],
            })

    def action_downgrade_to_portal(self):
        """將 partner 對應的用戶降級為純 Portal

        移除所有 membership group（Silver、Gold），
        並明確確保 Portal group 被保留（避免 implied_ids
        反向移除後失去 Portal 存取權）。
        僅限會員等級管理員呼叫。

        :raises AccessError: 呼叫者不是會員等級管理員時拋出
        """
        self._check_membership_manager()
        membership_groups = self._get_membership_groups()
        portal_group = self.env.ref('base.group_portal')
        for partner in self:
            users = partner.user_ids
            if not users:
                continue
            cmds = [(3, g.id) for g in membership_groups]
            # 明確確保 Portal group 被保留
            cmds.append((4, portal_group.id))
            users.sudo().write({
                'groups_id': cmds,
            })
