# -*- coding: utf-8 -*-
{
    'name': 'Woow Website Auth',
    'version': '18.0.1.3.0',
    'category': 'Website',
    'summary': '網站頁面統一存取控制',
    'description': """
        為會員制網站提供動態與靜態頁面的統一存取控制。
        管理員可在後台統一管理所有頁面的存取權限。
    """,
    'author': 'WoowTech',
    'website': 'https://www.woowtech.com',
    'license': 'LGPL-3',
    'depends': ['website'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/website_auth_rule_views.xml',
        'views/access_denied.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
