# -*- coding: utf-8 -*-
"""網站存取控制規則模型

定義 woow.website.auth.rule，用於管理靜態與動態頁面的存取控制規則。
包含規則的 CRUD、靜態頁面同步邏輯、以及 ormcache 快取機制。
"""

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import ormcache

from .ir_http import _BYPASS_PREFIXES, normalize_prefix

# path_prefix 不允許出現的字元：query／fragment 分隔字元
_PREFIX_FORBIDDEN_CHARS = ('?', '#')


class WoowWebsiteAuthRule(models.Model):
    """網站存取控制規則"""

    _name = 'woow.website.auth.rule'
    _description = '網站頁面存取控制規則'
    _order = 'sequence, id'

    # ----------------------------------------------------------------
    # 基本欄位
    # ----------------------------------------------------------------
    sequence = fields.Integer(
        string='排序',
        default=10,
        help='動態頁面：多條規則命中時以最長的 URL 前綴優先，'
             '前綴長度相同時才依此排序（數字越小優先級越高）；'
             '靜態頁面：同一頁面有多條規則時依此排序。拖曳可調整順序',
    )
    name = fields.Char(
        string='規則名稱',
        required=True,
    )
    active = fields.Boolean(
        string='啟用',
        default=True,
    )
    website_id = fields.Many2one(
        'website',
        string='網站',
        help='留空代表適用於所有網站',
    )

    # ----------------------------------------------------------------
    # 頁面類型
    # ----------------------------------------------------------------
    page_type = fields.Selection(
        [
            ('dynamic', '動態頁面'),
            ('static', '靜態頁面'),
        ],
        string='頁面類型',
        required=True,
        default='dynamic',
    )
    path_prefix = fields.Char(
        string='URL 前綴',
        help='動態頁面使用，例如 /appointment。\n'
             '比對有邊界且區分大小寫：/event 匹配 /event 與 /event/...，'
             '不匹配 /eventx；同一個 controller 的其他路由別名'
             '（例如 /events、/events/page/2）也會一併套用此規則。\n'
             '同一條路徑有多條規則命中時，最長的前綴優先；長度相同時才依排序。'
             '請求路徑與各別名各自選出的規則必須全部通過。\n'
             '存檔時會去掉尾端的 /；不可為 /，不可含 ?、# 或空白。',
    )
    website_page_id = fields.Many2one(
        'website.page',
        string='靜態頁面',
        help='選擇要保護的靜態頁面',
        ondelete='set null',
    )

    # ----------------------------------------------------------------
    # 驗證模式
    # ----------------------------------------------------------------
    auth_mode = fields.Selection(
        [
            ('signed_in', '任何登入用戶'),
            ('group', '指定群組'),
            ('multi_group', '多群組（任一）'),
        ],
        string='驗證模式',
        required=True,
        default='signed_in',
    )
    group_id = fields.Many2one(
        'res.groups',
        string='指定群組',
        help='auth_mode 為「指定群組」時使用',
    )
    group_ids = fields.Many2many(
        'res.groups',
        'woow_website_auth_rule_groups_rel',
        'rule_id',
        'group_id',
        string='群組清單',
        help='auth_mode 為「多群組」時使用，用戶屬於任一群組即可通過',
    )

    # ----------------------------------------------------------------
    # 顯示用欄位
    # ----------------------------------------------------------------
    display_path = fields.Char(
        string='路徑',
        compute='_compute_display_path',
    )

    # ----------------------------------------------------------------
    # 拒絕行為
    # ----------------------------------------------------------------
    deny_action = fields.Selection(
        [
            ('redirect_login', '導向登入頁'),
            ('redirect_custom', '導向自訂 URL'),
            ('render_403', '顯示 403 頁面'),
        ],
        string='拒絕行為',
        required=True,
        default='redirect_login',
    )
    redirect_url = fields.Char(
        string='導向 URL',
        help='deny_action 為「導向自訂 URL」時使用，例如 /membership/upgrade',
    )

    # ================================================================
    # Computed Fields
    # ================================================================

    @api.depends('page_type', 'path_prefix', 'website_page_id', 'website_page_id.url')
    def _compute_display_path(self):
        """計算顯示用路徑，依 page_type 顯示 path_prefix 或 website.page 的 URL"""
        for rule in self:
            if rule.page_type == 'dynamic':
                rule.display_path = rule.path_prefix or ''
            elif rule.page_type == 'static' and rule.website_page_id:
                rule.display_path = rule.website_page_id.url or rule.website_page_id.name
            else:
                rule.display_path = ''

    # ================================================================
    # Constraints
    # ================================================================

    @api.constrains('page_type', 'auth_mode')
    def _check_static_multi_group(self):
        """靜態頁面不支援 multi_group 驗證模式

        Odoo 原生 website.page 的 groups_id 只支援單一 group，
        因此靜態頁面規則的 auth_mode 不允許 multi_group。
        """
        for rule in self:
            if rule.page_type == 'static' and rule.auth_mode == 'multi_group':
                raise ValidationError(
                    _('Static pages do not support multi-group auth mode. '
                      'Rule: %s', rule.name)
                )

    @api.constrains('page_type', 'website_page_id')
    def _check_static_page_required(self):
        """靜態頁面規則必須選擇一個 website.page"""
        for rule in self:
            if rule.page_type == 'static' and not rule.website_page_id:
                raise ValidationError(
                    _('Static page rules require selecting a page. Rule: %s',
                      rule.name)
                )

    @api.constrains('auth_mode', 'group_id')
    def _check_group_required(self):
        """auth_mode 為 group 時必須指定 group_id"""
        for rule in self:
            if rule.auth_mode == 'group' and not rule.group_id:
                raise ValidationError(
                    _('Group auth mode requires selecting a group. Rule: %s',
                      rule.name)
                )

    @api.constrains('auth_mode', 'group_ids')
    def _check_multi_group_required(self):
        """auth_mode 為 multi_group 時必須至少指定一個 group"""
        for rule in self:
            if rule.auth_mode == 'multi_group' and not rule.group_ids:
                raise ValidationError(
                    _('Multi-group auth mode requires at least one group. '
                      'Rule: %s', rule.name)
                )

    @api.constrains('deny_action', 'redirect_url')
    def _check_redirect_url(self):
        """deny_action 為 redirect_custom 時必須提供 redirect_url"""
        for rule in self:
            if rule.deny_action == 'redirect_custom' and not rule.redirect_url:
                raise ValidationError(
                    _('Custom redirect requires a URL. Rule: %s', rule.name)
                )

    @api.constrains('redirect_url')
    def _check_redirect_url_xss(self):
        """Block dangerous URL schemes to prevent XSS attacks.

        Reject javascript:, data:, and vbscript: URL schemes which could
        be used for cross-site scripting if rendered in a browser redirect.
        """
        _dangerous_schemes = ('javascript:', 'data:', 'vbscript:')
        for rule in self:
            if not rule.redirect_url:
                continue
            url_lower = rule.redirect_url.strip().lower()
            # Also handle obfuscation attempts with leading whitespace/control chars
            url_cleaned = ''.join(url_lower.split())
            for scheme in _dangerous_schemes:
                if url_cleaned.startswith(scheme):
                    raise ValidationError(
                        _('Redirect URL contains a dangerous scheme '
                          '(%(scheme)s). Rule: %(rule)s',
                          scheme=scheme.rstrip(':'),
                          rule=rule.name)
                    )

    @api.constrains('page_type', 'path_prefix')
    def _check_path_prefix(self):
        """動態頁面的 path_prefix 必須以 / 開頭

        確保 path_prefix 格式正確，防止無效的 URL 前綴規則。
        """
        for rule in self:
            if rule.page_type != 'dynamic':
                continue
            if not rule.path_prefix:
                raise ValidationError(
                    _('Dynamic page rules require a URL prefix. Rule: %s',
                      rule.name)
                )
            prefix = rule.path_prefix
            if not prefix.startswith('/'):
                raise ValidationError(
                    _('URL prefix must start with /. Rule: %s', rule.name)
                )
            if any(ch.isspace() for ch in prefix):
                raise ValidationError(
                    _('URL prefix must not contain whitespace. Rule: %s',
                      rule.name)
                )
            if any(ch in prefix for ch in _PREFIX_FORBIDDEN_CHARS):
                raise ValidationError(
                    _('URL prefix must not contain "?" or "#" (query strings '
                      'and fragments are not matched). Rule: %s', rule.name)
                )
            if not prefix.strip('/'):
                raise ValidationError(
                    _('URL prefix "/" is not allowed: it would only match the '
                      'homepage, not the whole site. Use a static page rule '
                      'for the homepage. Rule: %s', rule.name)
                )
            if '//' in prefix or prefix != normalize_prefix(prefix):
                raise ValidationError(
                    _('URL prefix must not contain empty segments ("//") or a '
                      'trailing "/". Rule: %s', rule.name)
                )
            if (prefix + '/').startswith(_BYPASS_PREFIXES):
                raise ValidationError(
                    _('URL prefix %(prefix)s is under a path that is never '
                      'intercepted (backend, assets, sitemap, login…), so the '
                      'rule would have no effect. Rule: %(rule)s',
                      prefix=prefix, rule=rule.name)
                )

    # ================================================================
    # CRUD 覆寫
    # ================================================================

    @api.model
    def _normalize_path_prefix_vals(self, vals):
        """存檔前正規化 path_prefix：去頭尾空白與尾端斜線（只剩 / 時保留，交給 constraint 拒絕）"""
        prefix = vals.get('path_prefix')
        if prefix and isinstance(prefix, str):
            vals['path_prefix'] = normalize_prefix(prefix)
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        """建立規則後，同步靜態頁面並清除快取"""
        vals_list = [self._normalize_path_prefix_vals(dict(vals)) for vals in vals_list]
        records = super().create(vals_list)
        records._sync_website_pages()
        self._clear_rule_cache()
        return records

    def write(self, vals):
        """更新規則時處理靜態頁面同步與快取清除

        特別處理：當 active 從 True 變為 False 時，還原靜態頁面為公開。
        """
        vals = self._normalize_path_prefix_vals(dict(vals))
        # 檢查是否有規則從啟用變為停用
        deactivating_static_rules = self.env['woow.website.auth.rule']
        if 'active' in vals and not vals['active']:
            deactivating_static_rules = self.filtered(
                lambda r: r.active and r.page_type == 'static' and r.website_page_id
            )

        result = super().write(vals)

        # 停用的靜態規則：還原頁面為公開
        if deactivating_static_rules:
            deactivating_static_rules._reset_website_pages()

        # 仍然啟用的規則：正常同步
        active_rules = self.filtered(lambda r: r.active)
        if active_rules:
            active_rules._sync_website_pages()

        self._clear_rule_cache()
        return result

    def unlink(self):
        """刪除規則前，還原靜態頁面為公開，並清除快取"""
        static_rules = self.filtered(
            lambda r: r.page_type == 'static' and r.website_page_id
        )
        if static_rules:
            static_rules._reset_website_pages()
        # 在 super().unlink() 刪除記錄前先取得 model 參照以清除快取
        RuleModel = self.env['woow.website.auth.rule']
        result = super().unlink()
        RuleModel._clear_rule_cache()
        return result

    # ================================================================
    # 靜態頁面同步邏輯
    # ================================================================

    def _sync_website_pages(self):
        """將規則的驗證模式同步到 website.page 的 visibility 與 groups_id

        同步方向：rule → website.page（單向）
        - auth_mode = signed_in → visibility = 'signed_in', groups_id = False
        - auth_mode = group → visibility = 'restricted_group', groups_id = group_id
        """
        for rule in self:
            if rule.page_type != 'static' or not rule.website_page_id:
                continue

            page = rule.website_page_id.sudo()
            if rule.auth_mode == 'signed_in':
                page.write({
                    'visibility': 'connected',
                    'groups_id': [(5, 0, 0)],
                })
            elif rule.auth_mode == 'group' and rule.group_id:
                page.write({
                    'visibility': 'restricted_group',
                    'groups_id': [(6, 0, [rule.group_id.id])],
                })

    def _reset_website_pages(self):
        """還原靜態頁面為公開狀態（安全版本）

        檢查同一頁面是否還有其他啟用中的規則：
        - 若有：重新同步到剩餘規則的設定
        - 若無：將 visibility 設為空字串（公開），清除 groups_id
        用於規則停用或刪除時。
        """
        for rule in self:
            if rule.page_type != 'static' or not rule.website_page_id:
                continue

            page = rule.website_page_id.sudo()
            # 查詢同一頁面是否還有其他啟用中的規則（排除當前規則）
            remaining_rule = self.sudo().search([
                ('id', '!=', rule.id),
                ('id', 'not in', self.ids),
                ('page_type', '=', 'static'),
                ('website_page_id', '=', rule.website_page_id.id),
                ('active', '=', True),
            ], order='sequence, id', limit=1)

            if remaining_rule:
                # 有其他規則存在，重新同步到該規則的設定
                remaining_rule._sync_website_pages()
            else:
                # 無其他規則，還原為公開
                page.write({
                    'visibility': '',
                    'groups_id': [(5, 0, 0)],
                })

    # ================================================================
    # 快取機制
    # ================================================================

    @api.model
    @ormcache('website_id')
    def _get_active_rules(self, website_id):
        """取得指定網站的所有啟用規則（依 sequence, id 排序）

        實際套用哪些規則由 ir.http 的 applicable_rules 決定（每條候選路徑
        各取最長前綴，同長度才看這裡的順序；選出的規則全部要通過）。path_prefix 會再正規化一次，
        讓升級前就存在、帶尾端斜線的舊資料也能正確比對。

        使用 ormcache 快取，避免每次 request 都查詢資料庫。
        回傳 dict 列表（而非 recordset），避免 recordset cache 問題。

        :param website_id: 網站 ID，0 代表不限網站
        :return: list of dict，每個 dict 包含規則的關鍵欄位
        """
        domain = [
            ('active', '=', True),
            ('page_type', '=', 'dynamic'),
        ]
        if website_id:
            domain.append(('website_id', 'in', [False, website_id]))
        else:
            domain.append(('website_id', '=', False))

        rules = self.sudo().search(domain, order='sequence, id')
        result = []
        for rule in rules:
            # 取得 group 的 xml_id 供 has_group() 使用
            group_xml_id = False
            if rule.auth_mode == 'group' and rule.group_id:
                external_ids = rule.group_id.get_external_id()
                group_xml_id = external_ids.get(rule.group_id.id, False)

            group_xml_ids = []
            if rule.auth_mode == 'multi_group' and rule.group_ids:
                for group in rule.group_ids:
                    ext_ids = group.get_external_id()
                    xml_id = ext_ids.get(group.id, False)
                    if xml_id:
                        group_xml_ids.append(xml_id)

            result.append({
                'id': rule.id,
                'path_prefix': normalize_prefix(rule.path_prefix),
                'auth_mode': rule.auth_mode,
                'deny_action': rule.deny_action,
                'redirect_url': rule.redirect_url or '',
                'group_xml_id': group_xml_id,
                'group_xml_ids': group_xml_ids,
            })
        return result

    def _clear_rule_cache(self):
        """清除規則快取，於規則異動時呼叫

        使用 registry.clear_cache() 清除 ormcache（Odoo 18 標準做法）。
        """
        self.env.registry.clear_cache()

    # ================================================================
    # Onchange
    # ================================================================

    @api.onchange('page_type')
    def _onchange_page_type(self):
        """切換頁面類型時重設相關欄位

        - 切換到 static：清除 path_prefix，若 auth_mode 為 multi_group 則重設為 signed_in
        - 切換到 dynamic：清除 website_page_id
        """
        if self.page_type == 'static':
            self.path_prefix = False
            if self.auth_mode == 'multi_group':
                self.auth_mode = 'signed_in'
                self.group_ids = [(5, 0, 0)]
        elif self.page_type == 'dynamic':
            self.website_page_id = False

    @api.onchange('auth_mode')
    def _onchange_auth_mode(self):
        """切換驗證模式時清除不相關的 group 欄位"""
        if self.auth_mode == 'signed_in':
            self.group_id = False
            self.group_ids = [(5, 0, 0)]
        elif self.auth_mode == 'group':
            self.group_ids = [(5, 0, 0)]
        elif self.auth_mode == 'multi_group':
            self.group_id = False
