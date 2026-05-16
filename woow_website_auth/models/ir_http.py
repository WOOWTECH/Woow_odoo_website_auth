# -*- coding: utf-8 -*-
"""動態頁面攔截引擎

繼承 ir.http，在 _frontend_pre_dispatch 階段攔截前台請求，
依照 woow.website.auth.rule 規則比對 URL prefix，
對未通過驗證的用戶執行相應的拒絕行為。
"""

import logging

import werkzeug

from odoo import models
from odoo.http import request

_logger = logging.getLogger(__name__)

# 不應被攔截的路徑前綴（後台、靜態資源、登入頁等）
_BYPASS_PREFIXES = (
    '/web/',
    '/website/translations',
    '/web/static/',
    '/web/assets/',
    '/web/content/',
    '/web/image/',
)


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _frontend_pre_dispatch(cls):
        """在前台請求分派前，攔截受保護的動態頁面

        攔截邏輯：
        1. 防禦性檢查：排除後台路徑與靜態資源
        2. 取得當前 website_id
        3. 從 cache 讀取 active 規則（僅動態頁面）
        4. 按 sequence 排序，逐條以 startswith 比對當前路徑
        5. 第一條命中即檢查權限，不通過則依 deny_action 處理
        """
        super()._frontend_pre_dispatch()

        path = request.httprequest.path

        # 防禦性檢查：排除後台路徑與靜態資源，避免誤擋後台功能
        if path.startswith(_BYPASS_PREFIXES):
            return

        # 取得當前 website（此時已由 website 模組設定完成）
        website = getattr(request, 'website', None)
        website_id = website.id if website else 0

        # 從 cache 取得規則列表
        RuleModel = request.env['woow.website.auth.rule']
        rules = RuleModel._get_active_rules(website_id)

        for rule in rules:
            prefix = rule['path_prefix']
            if not prefix or not path.startswith(prefix):
                continue

            # 命中規則，檢查權限
            if not cls._check_auth(rule):
                cls._deny_access(rule, path)

            # 第一條命中即停止（不論是否通過檢查）
            return

    @classmethod
    def _check_auth(cls, rule):
        """檢查當前用戶是否通過規則的驗證

        :param rule: dict，規則資料（來自 _get_active_rules cache）
        :return: True 表示通過，False 表示不通過
        """
        user = request.env.user

        auth_mode = rule['auth_mode']

        if auth_mode == 'signed_in':
            # 任何已登入用戶即可通過
            return not user._is_public()

        elif auth_mode == 'group':
            # 未登入直接拒絕
            if user._is_public():
                return False
            xml_id = rule.get('group_xml_id')
            if not xml_id:
                return False
            return user.has_group(xml_id)

        elif auth_mode == 'multi_group':
            # 未登入直接拒絕
            if user._is_public():
                return False
            xml_ids = rule.get('group_xml_ids', [])
            if not xml_ids:
                return False
            # 任一 group 命中即通過
            return any(user.has_group(xml_id) for xml_id in xml_ids)

        # 未知的 auth_mode：安全起見放行（不應發生）
        _logger.warning(
            'woow_website_auth: unknown auth_mode %r for rule %s, allowing access',
            auth_mode, rule.get('id'),
        )
        return True

    @classmethod
    def _deny_access(cls, rule, path):
        """依據規則的 deny_action 執行拒絕行為

        :param rule: dict，規則資料
        :param path: str，當前請求路徑
        :raises werkzeug.exceptions.Forbidden: 作為未知 deny_action 的安全 fallback
        """
        deny_action = rule['deny_action']

        if deny_action == 'redirect_login':
            # 導向登入頁，帶 redirect 參數以便登入後返回原路徑
            login_url = '/web/login?redirect=%s' % werkzeug.urls.url_quote(path)
            raise werkzeug.exceptions.HTTPException(
                response=request.redirect(login_url, local=True)
            )

        elif deny_action == 'redirect_custom':
            # 導向自訂 URL
            redirect_url = rule.get('redirect_url', '/')
            raise werkzeug.exceptions.HTTPException(
                response=request.redirect(redirect_url, local=True)
            )

        elif deny_action == 'render_403':
            # 顯示 403 禁止存取頁面
            raise werkzeug.exceptions.Forbidden()

        else:
            # 未知的 deny_action：安全 fallback，阻止存取
            _logger.warning(
                'woow_website_auth: unknown deny_action %r for rule %s, denying access',
                deny_action, rule.get('id'),
            )
            raise werkzeug.exceptions.Forbidden()
