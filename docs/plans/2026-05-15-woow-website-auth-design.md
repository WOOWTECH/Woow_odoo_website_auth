# woow_website_auth 模組設計文件

## 概述

為 WoowTech（渥屋科技）開發的 Odoo 18 Community 模組，提供會員制網站的統一頁面存取控制。管理員可在後台統一管理所有靜態與動態頁面的存取權限。

- 授權：LGPL-3
- 依賴：僅 `website`（Odoo 原生）
- 無 OCA 依賴，從零開發

---

## 設計決議

| # | 議題 | 決議 |
|---|------|------|
| 1 | `deny_action` 選項 | 合併成 3 個：`redirect_login`、`redirect_custom`、`render_403`，搭配 `redirect_url` char 欄位 |
| 2 | 刪除 rule 時靜態頁面行為 | 還原為公開（`visibility` 清空、`groups_id` 清空） |
| 3 | 停用 rule（`active=False`）時靜態頁面行為 | 還原為公開（與刪除一致） |
| 4 | `path_prefix` 比對邏輯 | 按 `sequence` 排序，`startswith` 比對，第一條命中即停止 |
| 5 | `default_rules.xml` | 不建立，安裝後規則列表為空 |
| 6 | Cache 機制 | 使用 `ormcache`，規則異動時 `registry.clear_cache()` |
| 7 | 判斷已登入 | 使用 `request.env.user._is_public()` |
| 8 | 判斷前台請求 | 使用 `request.is_frontend`，hook 點實作時驗證 |

---

## 檔案結構

```
woow_website_auth/
├── __init__.py
├── __manifest__.py
├── security/
│   ├── security.xml            # group 定義與 category
│   └── ir.model.access.csv     # model 存取權限
├── models/
│   ├── __init__.py
│   ├── website_auth_rule.py    # 規則 model + sync 邏輯 + cache
│   ├── ir_http.py              # 動態頁面攔截引擎
│   └── res_partner.py          # 會員升級 API
└── views/
    ├── website_auth_rule_views.xml  # tree + form view
    └── menu.xml                     # 選單定義
```

---

## 開發順序與各檔案內容

### Step 1：`__manifest__.py`

模組宣告檔：

```python
{
    'name': 'Woow Website Auth',
    'version': '18.0.1.0.0',
    'category': 'Website',
    'summary': '網站頁面統一存取控制',
    'author': 'WoowTech',
    'license': 'LGPL-3',
    'depends': ['website'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/website_auth_rule_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': False,
}
```

### Step 2：`security/security.xml`

定義 Membership category 與三層會員 group：

- `ir.module.category` → `module_category_membership`
- `group_member_silver`：implies `base.group_portal`
- `group_member_gold`：implies `group_member_silver`

### Step 3：`security/ir.model.access.csv`

`woow.website.auth.rule` 的存取權限：

| Group | Read | Write | Create | Unlink |
|-------|------|-------|--------|--------|
| `base.group_system` | 1 | 1 | 1 | 1 |
| `base.group_website_designer` | 1 | 1 | 1 | 1 |
| 其他 | 0 | 0 | 0 | 0 |

### Step 4：`models/website_auth_rule.py`

核心規則 model `woow.website.auth.rule`：

**欄位：**

| 欄位 | 類型 | 說明 |
|------|------|------|
| `sequence` | Integer | 排序/優先級，default=10 |
| `name` | Char | 規則名稱，required |
| `active` | Boolean | 啟用/停用，default=True |
| `website_id` | Many2one → `website` | 多站點支援，留空=所有站點 |
| `page_type` | Selection | `dynamic` / `static`，required |
| `path_prefix` | Char | 動態頁面用，URL 前綴 |
| `website_page_id` | Many2one → `website.page` | 靜態頁面用 |
| `auth_mode` | Selection | `signed_in` / `group` / `multi_group` |
| `group_id` | Many2one → `res.groups` | `group` 模式用 |
| `group_ids` | Many2many → `res.groups` | `multi_group` 模式用（僅動態） |
| `deny_action` | Selection | `redirect_login` / `redirect_custom` / `render_403` |
| `redirect_url` | Char | `redirect_custom` 時的目標 URL |

**核心邏輯：**

1. `create()` / `write()`：
   - 儲存後觸發 `_sync_website_page()` 同步靜態頁面
   - 呼叫 `self.env.registry.clear_cache()` 清除 ormcache

2. `unlink()`：
   - 刪除前先還原靜態頁面為公開
   - 清除 cache

3. `write()` 中 `active` 變為 `False` 時：
   - 還原靜態頁面為公開

4. `_sync_website_page()`：
   - `auth_mode = signed_in` → `page.visibility = 'signed_in'`, `page.groups_id = False`
   - `auth_mode = group` → `page.visibility = 'restricted_group'`, `page.groups_id = self.group_id`

5. `_get_active_rules(website_id)`：
   - 使用 `@ormcache('website_id')` 裝飾
   - 回傳排序後的 active 規則列表（dict 形式，避免 recordset cache 問題）

### Step 5：`models/ir_http.py`

動態頁面攔截引擎，繼承 `ir.http`：

**邏輯流程：**

```
_dispatch()
  ├─ 呼叫 super()._dispatch()... 不對，要在 super 之前攔截
  ├─ 判斷 is_frontend
  ├─ 用 sudo() 讀取 active rules（從 cache）
  ├─ 按 sequence 排序，逐條 startswith 比對
  ├─ 第一條命中：
  │   ├─ auth_mode = signed_in → 檢查 _is_public()
  │   ├─ auth_mode = group → 檢查 user.has_group(xml_id)
  │   ├─ auth_mode = multi_group → 檢查任一 group
  │   └─ 不通過時依 deny_action 處理：
  │       ├─ redirect_login → redirect /web/login?redirect=path
  │       ├─ redirect_custom → redirect redirect_url
  │       └─ render_403 → raise 403
  └─ 無命中 → 正常 super()._dispatch()
```

**重要注意事項：**

- 攔截時機：需在 controller 處理之前。具體 hook 點（`_dispatch` vs `_frontend_pre_dispatch`）實作時驗證
- 規則讀取必須 `sudo()` 避免 public user 權限問題
- `has_group()` 使用 xml_id，需透過 `get_external_id()` 取得
- website_id 過濾：規則的 `website_id` 為空或等於當前 website

### Step 6：`views/website_auth_rule_views.xml`

**Tree View：**
- 欄位：sequence（handle）、name、page_type、path_prefix（`page_type=dynamic` 時顯示）、website_page_id（`page_type=static` 時顯示）、auth_mode、group_id、active
- 支援拖曳排序

**Form View：**
- `page_type` 切換：
  - `dynamic` → 顯示 `path_prefix`，隱藏 `website_page_id`
  - `static` → 顯示 `website_page_id`，隱藏 `path_prefix`
- `auth_mode` 切換：
  - `signed_in` → 隱藏所有 group 欄位
  - `group` → 顯示 `group_id`
  - `multi_group` → 顯示 `group_ids`（僅 `page_type=dynamic` 時可選）
- `deny_action` 切換：
  - `redirect_custom` → 顯示 `redirect_url`
  - 其他 → 隱藏 `redirect_url`

**`auth_mode` 的 `multi_group` 選項在 `page_type=static` 時隱藏：**
- 使用 `@api.onchange('page_type')` 在切換到 static 時，若 `auth_mode` 為 `multi_group` 則自動重設為 `signed_in`
- View 層使用 `invisible` attribute 控制顯示

### Step 7：`views/menu.xml`

選單位置：`Website > Configuration > Auth Rules`

- 父選單：`website.menu_website_configuration`
- action：指向 `woow.website.auth.rule` 的 tree/form view

### Step 8：`models/res_partner.py`

在 `res.partner` 上新增三個方法：

- `action_upgrade_to_silver()`：加入 Silver group（透過 `users.groups_id`）
- `action_upgrade_to_gold()`：加入 Gold group（implied_ids 自動包含 Silver）
- `action_downgrade_to_portal()`：移除所有 membership group

使用 `self.env.ref()` 取得 group reference，不硬編 xml_id 字串（定義為 model 層常數或方法）。

---

## 驗收場景

### 動態頁面

1. 未登入 → `/appointment` → 導向 `/web/login?redirect=/appointment`
2. Portal user → `/appointment`（規則要求 Silver）→ 導向 `/membership/upgrade`
3. Silver member → `/appointment` → 正常顯示
4. Gold member → `/appointment/vip` → 正常顯示
5. Silver member → `/appointment/vip`（規則要求 Gold）→ 導向 `/membership/upgrade`
6. 規則 `active=False` → 路徑不再受保護

### 靜態頁面

1. rule `signed_in` 儲存 → `page.visibility = 'signed_in'`, `groups_id = False`
2. rule `group = Silver` 儲存 → `page.visibility = 'restricted_group'`, `groups_id = Silver`
3. rule 停用 → `page.visibility` 清空, `groups_id` 清空
4. rule 刪除 → 同上
5. `page_type = static` 時 → `auth_mode` 不出現 `multi_group`

### UI 行為

1. `page_type` 切換 → 正確顯示/隱藏路徑欄位
2. `auth_mode` 切換 → 正確顯示/隱藏 group 欄位
3. `deny_action` 切換 → 正確顯示/隱藏 `redirect_url`
