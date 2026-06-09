# -*- coding: utf-8 -*-
"""會員升級/降級 Public API

在 res.partner 上提供會員等級操作方法，
供外部系統（含 AI/LLM）透過 JSON-RPC call_kw 呼叫。
僅限 internal user（base.group_user）以上權限呼叫，
防止 portal user 透過 RPC 自行提權。
"""

from odoo import _, models
from odoo.exceptions import AccessError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def _check_membership_manager(self):
        """檢查當前用戶是否具有 internal user 以上權限

        僅 internal user（base.group_user）以上可執行會員升級/降級操作，
        防止 portal user 透過 JSON-RPC 自行提權。
        admin、專用 API 帳號、AI/LLM bot 帳號皆可通過。

        :raises AccessError: portal user 或 public user 呼叫時拋出
        """
        if not self.env.user.has_group('base.group_user'):
            raise AccessError(
                _('Only internal users can modify membership levels.')
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
        僅限 internal user 以上權限呼叫。

        :raises AccessError: portal/public user 呼叫時拋出
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
        僅限 internal user 以上權限呼叫。

        :raises AccessError: portal/public user 呼叫時拋出
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
        僅限 internal user 以上權限呼叫。

        :raises AccessError: portal/public user 呼叫時拋出
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
