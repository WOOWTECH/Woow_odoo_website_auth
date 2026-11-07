# -*- coding: utf-8 -*-
"""18.0.1.3.1：正規化既有動態規則的 path_prefix

- 去掉頭尾空白與尾端斜線（'/event/' → '/event'）。舊版比對時會變成
  '/event//'，規則永遠不命中；正規化後規則開始生效（屬預期的行為改變）。
- 只剩斜線的 '/' 保持不動（執行時仍只匹配首頁，與舊版相同），只記 warning。
- 含 ?、#、內部空白、或落在不攔截路徑下的前綴不改值，只記 warning，
  讓管理員自行修正（下次存檔時 constraint 會要求修正）。

可重複執行：已正規化的資料不會再被更新。
"""

import logging

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


def migrate(cr, version):
    if not version:
        return
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
