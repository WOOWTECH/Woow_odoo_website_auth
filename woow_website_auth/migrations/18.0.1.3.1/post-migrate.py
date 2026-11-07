# -*- coding: utf-8 -*-
"""18.0.1.3.1：正規化既有動態規則的 path_prefix；把 admin 加入會員等級管理員

- base.user_admin 加入 group_membership_manager：security.xml 把這筆放在
  noupdate="1"，而 noupdate 資料在 -u 時不會套用到已存在的 xmlid，所以從舊版
  升級時在這裡補一次；新安裝由 security.xml 處理。admin 若屬於
  base.group_erp_manager，本來就會因隱含關係擁有此群組。

- 去掉頭尾空白與尾端斜線（'/event/' → '/event'）。舊版比對時會變成
  '/event//'，規則永遠不命中；正規化後規則開始生效（屬預期的行為改變）。
- 只剩斜線的 '/' 保持不動，只記 warning。執行時它匹配首頁，以及路由以
  轉換器開頭（例如 ``/<model(...):x>``，靜態部分為 ``/``）的 endpoint；
  不會變成全站規則。
- 含 ?、#、內部空白、或落在不攔截路徑下的前綴不改值，只記 warning，
  讓管理員自行修正（下次存檔時 constraint 會要求修正）。

可重複執行：已正規化的資料不會再被更新。
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

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


def _normalize(prefix):
    prefix = (prefix or '').strip()
    if not prefix:
        return ''
    return prefix.rstrip('/') or '/'


def _add_admin_to_membership_manager(cr):
    env = api.Environment(cr, SUPERUSER_ID, {})
    group = env.ref('woow_website_auth.group_membership_manager', raise_if_not_found=False)
    admin = env.ref('base.user_admin', raise_if_not_found=False)
    if not group or not admin or group in admin.groups_id:
        return
    # ORM 寫入：會一併清除 has_group 等快取
    admin.write({'groups_id': [(4, group.id)]})
    _logger.info('woow_website_auth: added base.user_admin to group_membership_manager')


def migrate(cr, version):
    if not version:
        return
    _add_admin_to_membership_manager(cr)
    cr.execute("""
        SELECT id, path_prefix
          FROM woow_website_auth_rule
         WHERE page_type = 'dynamic'
           AND path_prefix IS NOT NULL
    """)
    changed = 0
    for rule_id, prefix in cr.fetchall():
        new_prefix = _normalize(prefix)
        if new_prefix and new_prefix != prefix:
            cr.execute(
                "UPDATE woow_website_auth_rule SET path_prefix = %s WHERE id = %s",
                (new_prefix, rule_id),
            )
            changed += 1
            _logger.info(
                'woow_website_auth: rule %s path_prefix normalized %r -> %r',
                rule_id, prefix, new_prefix,
            )
        check = new_prefix or prefix
        problems = []
        if check == '/':
            problems.append("'/' only matches the homepage")
        if any(ch in check for ch in ('?', '#')):
            problems.append("contains '?' or '#' (never matches)")
        if any(ch.isspace() for ch in check):
            problems.append('contains whitespace (never matches)')
        if (check + '/').startswith(_BYPASS_PREFIXES):
            problems.append('is under a never-intercepted path (no effect)')
        if problems:
            _logger.warning(
                'woow_website_auth: rule %s path_prefix %r needs review: %s',
                rule_id, check, '; '.join(problems),
            )
    if changed:
        _logger.info('woow_website_auth: normalized %d path_prefix value(s)', changed)
