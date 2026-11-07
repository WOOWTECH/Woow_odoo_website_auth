# -*- coding: utf-8 -*-
"""動態頁面攔截引擎

繼承 ir.http，在 _frontend_pre_dispatch 階段攔截前台請求，
依照 woow.website.auth.rule 規則比對 URL prefix，
對未通過驗證的用戶執行相應的拒絕行為。

比對規則（18.0.1.3.1 起）：

1. 候選路徑 = 本次請求路徑，加上「命中 endpoint 的所有註冊路由」的靜態部分
   （第一個 ``<`` 之前）。同一個 controller 方法以多個路由註冊時
   （例如 website_event 的 ``/event``、``/events``、``/events/page/<int:page>``），
   只要任一別名落在規則前綴內，整個 endpoint 都套用該規則。
2. 前綴比對有邊界：``/app`` 只匹配 ``/app`` 與 ``/app/...``，不匹配 ``/application``。
3. **每一條候選路徑各自**取最長前綴的規則（前綴長度相同時才依 sequence、id 決定）。
   最長前綴只在「同一條路徑」的規則之間比較：較窄的規則可以放寬它真正涵蓋的
   路徑，但不能透過別名放寬別的路徑。
4. 各候選路徑選出的規則**全部都要通過**才放行（fail closed）；任一條拒絕就依
   那條規則的 deny_action 處理，請求路徑本身選出的規則優先。
   例：``/event``（Silver）＋``/event/page``（已登入）時，``/event`` 與 ``/events``
   都要 Silver。
5. 未知的 auth_mode／deny_action 一律拒絕（fail closed）。
"""

import logging
import re
from urllib.parse import urlsplit

import werkzeug
import werkzeug.exceptions
import werkzeug.urls

from odoo import models
from odoo.http import request

_logger = logging.getLogger(__name__)

# 不應被攔截的路徑前綴（後台、靜態資源、SEO、登入頁等）
# 注意：落在這些前綴下的規則永遠不會生效，規則存檔時會被拒絕
# （見 woow.website.auth.rule._check_path_prefix）。
_BYPASS_PREFIXES = (
    '/web/',
    '/website/translations',
    '/website/action/',
    '/web/static/',
    '/web/assets/',
    '/web/content/',
    '/web/image/',
    '/website/access-denied',
    '/sitemap',
    '/_service_worker',
)

# request 上暫存本次命中的 werkzeug Rule（由 _pre_dispatch 設定）
_ROUTING_RULE_ATTR = '_woow_website_auth_routing_rule'

_MULTI_SLASH_RE = re.compile(r'/{2,}')


def normalize_prefix(prefix):
    """將規則前綴正規化：去頭尾空白、去尾端斜線；只剩斜線時視為 ``/``

    :param prefix: str 或 False
    :return: str（可能為空字串，代表沒有前綴）
    """
    if not prefix:
        return ''
    prefix = prefix.strip()
    if not prefix:
        return ''
    return prefix.rstrip('/') or '/'


def normalize_path(path):
    """將請求路徑正規化：合併連續斜線，非根路徑去掉尾端斜線"""
    if not path:
        return '/'
    path = _MULTI_SLASH_RE.sub('/', path)
    return path.rstrip('/') or '/'


def path_under_prefix(path, prefix):
    """邊界感知比對：path 等於 prefix，或位於 prefix + '/' 之下"""
    if not prefix:
        return False
    return path == prefix or path.startswith(prefix + '/')


def route_static_prefix(route):
    """取得路由字串在第一個 ``<`` 之前的靜態部分（已正規化）

    ``/event/page/<int:page>`` → ``/event/page``；``/events`` → ``/events``；
    ``/<path:page>`` → ``/``。
    """
    static = (route or '').split('<', 1)[0]
    return normalize_path(static)


def candidate_paths(path, routing_rule=None):
    """組出用來比對規則的候選路徑

    :param path: 本次請求路徑
    :param routing_rule: 命中的 werkzeug Rule（可為 None，例如 fallback 的
        website.page 或 404）；會讀取 ``rule.endpoint.routing['routes']``
    :return: list of str（去重、保持順序）
    """
    paths = [normalize_path(path)]
    endpoint = getattr(routing_rule, 'endpoint', None)
    routing = getattr(endpoint, 'routing', None) or {}
    routes = routing.get('routes') or []
    if isinstance(routes, str):
        routes = [routes]
    # werkzeug Rule 本身的路由字串（保險：routes 沒列到時也納入）
    rule_str = getattr(routing_rule, 'rule', None)
    if isinstance(rule_str, str):
        routes = list(routes) + [rule_str]
    for route in routes:
        static = route_static_prefix(route)
        if static not in paths:
            paths.append(static)
    return paths


def match_rule(rules, path):
    """找出涵蓋「單一路徑」的規則：最長前綴優先

    長度相同時取 rules 中較前面的（rules 已依 sequence, id 排序）。

    :param rules: list of dict（來自 _get_active_rules）
    :param path: str，已正規化的路徑
    :return: dict 或 None
    """
    best = None
    best_len = -1
    for rule in rules:
        prefix = normalize_prefix(rule.get('path_prefix'))
        if not prefix or len(prefix) <= best_len:
            continue
        if path_under_prefix(path, prefix):
            best = rule
            best_len = len(prefix)
    return best


def applicable_rules(rules, paths):
    """每條候選路徑各自選出最長前綴的規則，去重後依候選順序回傳

    第一條候選路徑是請求路徑本身，所以它選出的規則排在最前面。
    呼叫端必須要求使用者**全部通過**（見模組說明第 4 點）。

    :param rules: list of dict（來自 _get_active_rules）
    :param paths: 候選路徑 list（candidate_paths 的結果）
    :return: list of dict
    """
    result = []
    seen = set()
    for path in paths:
        rule = match_rule(rules, path)
        if rule is None:
            continue
        key = rule.get('id') or id(rule)
        if key in seen:
            continue
        seen.add(key)
        result.append(rule)
    return result


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _pre_dispatch(cls, rule, args):
        """記下本次命中的路由，讓 _frontend_pre_dispatch 能比對 endpoint 的所有別名"""
        setattr(request, _ROUTING_RULE_ATTR, rule)
        super()._pre_dispatch(rule, args)

    @classmethod
    def _frontend_pre_dispatch(cls):
        """在前台請求分派前，攔截受保護的動態頁面

        攔截邏輯：
        1. 防禦性檢查：排除後台路徑與靜態資源
        2. 取得當前 website_id
        3. 從 cache 讀取 active 規則（僅動態頁面）
        4. 以請求路徑＋命中 endpoint 的所有路由別名，每條各取最長前綴的規則
        5. 所有選出的規則都要通過；任一條不通過則依該規則的 deny_action 處理
        """
        super()._frontend_pre_dispatch()

        path = request.httprequest.path

        # 防禦性檢查：排除後台路徑與靜態資源，避免誤擋後台功能
        if path.startswith(_BYPASS_PREFIXES):
            return

        paths = candidate_paths(path, getattr(request, _ROUTING_RULE_ATTR, None))
        for rule in cls._woow_find_rules(paths):
            if not cls._check_auth(rule):
                cls._deny_access(rule, path)

    @classmethod
    def _woow_find_rules(cls, paths):
        """依候選路徑找出當前網站要套用的規則（list of dict，請求路徑的規則在前）"""
        # 取得當前 website（此時已由 website 模組設定完成）
        website = getattr(request, 'website', None)
        website_id = website.id if website else 0
        rules = request.env['woow.website.auth.rule']._get_active_rules(website_id)
        return applicable_rules(rules, paths)

    @classmethod
    def _woow_denying_rule(cls, paths, user):
        """回傳第一條會拒絕 user 的規則（沒有則 None）"""
        for rule in cls._woow_find_rules(paths):
            if not cls._woow_rule_allows(rule, user):
                return rule
        return None

    @classmethod
    def _woow_routing_rule_for(cls, path):
        """查出 path 會命中的 werkzeug Rule（只讀路由表，無副作用；查不到回 None）"""
        try:
            adapter = request.env['ir.http'].routing_map().bind_to_environ(
                request.httprequest.environ)
            rule, _args = adapter.match(path_info=path, return_rule=True)
            return rule
        except werkzeug.exceptions.HTTPException:
            # NotFound／MethodNotAllowed／RequestRedirect：退回只看字面路徑
            return None
        except Exception:  # noqa: BLE001 — 路由轉換器出錯時不影響導向判斷
            _logger.debug('woow_website_auth: cannot match %s', path, exc_info=True)
            return None

    @classmethod
    def _check_auth(cls, rule):
        """檢查當前用戶是否通過規則的驗證

        :param rule: dict，規則資料（來自 _get_active_rules cache）
        :return: True 表示通過，False 表示不通過
        """
        return cls._woow_rule_allows(rule, request.env.user)

    @classmethod
    def _woow_rule_allows(cls, rule, user):
        """判斷 user 是否通過 rule；未知 auth_mode 一律拒絕（fail closed）"""
        auth_mode = rule.get('auth_mode')

        if auth_mode == 'signed_in':
            # 任何已登入用戶即可通過
            return not user._is_public()

        if auth_mode == 'group':
            # 未登入直接拒絕
            if user._is_public():
                return False
            xml_id = rule.get('group_xml_id')
            if not xml_id:
                return False
            return user.has_group(xml_id)

        if auth_mode == 'multi_group':
            # 未登入直接拒絕
            if user._is_public():
                return False
            xml_ids = rule.get('group_xml_ids') or []
            if not xml_ids:
                return False
            # 任一 group 命中即通過
            return any(user.has_group(xml_id) for xml_id in xml_ids)

        # 未知的 auth_mode：安全起見拒絕
        _logger.warning(
            'woow_website_auth: unknown auth_mode %r for rule %s, denying access',
            auth_mode, rule.get('id'),
        )
        return False

    @classmethod
    def _deny_access(cls, rule, path):
        """依據規則的 deny_action 執行拒絕行為

        :param rule: dict，規則資料
        :param path: str，當前請求路徑
        :raises werkzeug.exceptions.Forbidden: 作為未知 deny_action 的安全 fallback
        """
        deny_action = rule.get('deny_action')
        user = request.env.user
        is_logged_in = not user._is_public()

        if deny_action == 'redirect_login':
            if is_logged_in:
                # 用戶已登入但無權限 → 導向存取拒絕頁面，避免重定向循環
                raise werkzeug.exceptions.HTTPException(
                    response=request.redirect('/website/access-denied', local=True)
                )
            # 未登入 → 導向登入頁，帶 redirect 參數以便登入後返回原路徑
            login_url = '/web/login?redirect=%s' % werkzeug.urls.url_quote(path)
            raise werkzeug.exceptions.HTTPException(
                response=request.redirect(login_url, local=True)
            )

        if deny_action == 'redirect_custom':
            redirect_url = rule.get('redirect_url') or '/'
            if cls._woow_redirect_loops(redirect_url, user):
                # 防止迴圈：導向目標本身也會被（同一條或另一條）規則拒絕 → 直接 403
                _logger.warning(
                    'woow_website_auth: redirect loop detected for rule %s '
                    '(path=%s, redirect=%s), returning 403',
                    rule.get('id'), path, redirect_url,
                )
                raise werkzeug.exceptions.Forbidden()
            raise werkzeug.exceptions.HTTPException(
                response=request.redirect(redirect_url, local=True)
            )

        if deny_action == 'render_403':
            # 顯示 403 禁止存取頁面
            raise werkzeug.exceptions.Forbidden()

        # 未知的 deny_action：安全 fallback，阻止存取
        _logger.warning(
            'woow_website_auth: unknown deny_action %r for rule %s, denying access',
            deny_action, rule.get('id'),
        )
        raise werkzeug.exceptions.Forbidden()

    @classmethod
    def _woow_redirect_loops(cls, redirect_url, user):
        """導向目標是否會再被規則拒絕（同一條規則或另一條規則）

        只看導向目標的路徑部分（去掉 scheme／host／query／fragment），
        並和一般請求一樣納入目標 endpoint 的所有路由別名。
        """
        target = urlsplit(redirect_url or '/').path or '/'
        if not target.startswith('/'):
            # 相對路徑：無法可靠判斷，交給 request.redirect(local=True) 處理
            return False
        if target.startswith(_BYPASS_PREFIXES):
            return False
        target = normalize_path(target)
        paths = candidate_paths(target, cls._woow_routing_rule_for(target))
        return cls._woow_denying_rule(paths, user) is not None
