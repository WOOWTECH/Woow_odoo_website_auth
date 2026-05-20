# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request


class WoowWebsiteAuthController(http.Controller):

    @http.route(
        '/website/access-denied',
        type='http',
        auth='public',
        website=True,
        sitemap=False,
    )
    def access_denied(self, **kwargs):
        """顯示存取拒絕頁面 — 當已登入用戶無權存取時導向此頁"""
        return request.render('woow_website_auth.access_denied_page', {})
