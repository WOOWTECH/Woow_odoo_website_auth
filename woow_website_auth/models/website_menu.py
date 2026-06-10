# -*- coding: utf-8 -*-
"""網站選單可見性控制

繼承 website.menu，覆寫 _compute_visible() 補全 group_ids 檢查邏輯。
Odoo 18 原生 website.menu 已有 group_ids 欄位，但 _compute_visible()
未使用它。本模組補全這個缺口，並整合 woow.website.auth.rule 的選單同步。
"""

from odoo import api, models


class WebsiteMenu(models.Model):
    _inherit = 'website.menu'

    def _compute_visible(self):
        """覆寫選單可見性計算，加入 group_ids 群組檢查

        邏輯順序：
        1. 先執行 Odoo 原生的 page/controller 可見性檢查
        2. 如果仍然可見且 group_ids 有值，檢查當前使用者是否屬於任一群組
        3. website.group_website_designer 永遠可見（write() 已確保 designer 在 group_ids 中）
        """
        super()._compute_visible()
        for menu in self:
            if not menu.is_visible:
                continue
            if not menu.group_ids:
                continue
            # group_ids 有值時，檢查使用者是否屬於任一群組
            menu.is_visible = bool(menu.group_ids & self.env.user.groups_id)
