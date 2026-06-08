---
module_technical_name: woow_snippet_builder
module_display_name: "WoOW Snippet Builder"
version: "18.0.2.0.0"
category: Website
license: LGPL-3
author: WoOW Technology
website: https://woowtech.com
depends:
  - website
application: true
installable: true
python_models: 0 new, 1 inherited
controllers: 1 class, 5 routes
js_widgets: 4 frontend widgets, 4 editor option classes
xml_templates: 6 QWeb dynamic filter templates, 5 view templates, 2 data files
snippet_count: 4
asset_bundles:
  web.assets_frontend: 4 JS files
  website.assets_wysiwyg: 4 JS files
---

# LLM Knowledge Base: woow_snippet_builder

> Provides 4 dynamic website snippets (Dynamic Content, Stat Card, Chart, Data Table) that integrate natively with the Odoo 18 website editor BLOCKS and CUSTOMIZE panels. All snippets are configured entirely within the website editor -- no backend navigation required. Data is fetched via JSON-RPC from a controller that enforces a model whitelist. The Dynamic Content snippet extends Odoo's native `DynamicSnippet` system with generic field mapping so a single set of QWeb templates renders records from any model.

---

## 1. MODULE OVERVIEW

### 1.1 Key Capabilities

| # | Capability | Implementation |
|---|-----------|---------------|
| 1 | Dynamic Content snippet | Extends native `DynamicSnippet`; generic field mapping (`field_0..N`, `image`); 6 QWeb layout templates; context/URL param filtering |
| 2 | Stat Card snippet | Aggregation endpoint (`count`, `sum`, `avg`, `min`, `max`, `count_distinct`); 4 sub-types (`default`, `progress`, `trend`, `threshold`); group-by breakdown |
| 3 | Chart snippet | Chart.js integration; 10 chart types; single-series and multi-series; gauge with center label; funnel as sorted horizontal bar |
| 4 | Data Table snippet | Paginated, searchable, sortable table; server-side search across char/text/html fields; up to 100 rows per page |
| 5 | Model whitelist | 28 models allowed by default; extensible via controller override |
| 6 | Editor integration | All 4 snippets have CUSTOMIZE panel options; dynamic field selects populated from RPC |

### 1.2 Anti-Features / Boundaries

- No new Odoo models are defined; only `website.snippet.filter` is inherited
- No access control (ir.model.access, ir.rule) records shipped; relies on `.sudo()` for public reads
- No CSS/SCSS files; all styling uses Bootstrap 5 utility classes
- No backend views (menus, actions, forms, trees)
- No cron jobs, mail templates, or workflow automations
- Chart.js is loaded from Odoo's bundled copy (`/web/static/lib/Chart/Chart.js`), not from CDN

---

## 2. DATA MODEL

### 2.1 Model: website.snippet.filter (inherited)

**File:** `models/website_snippet_filter.py`
**Inheritance:** `_inherit = 'website.snippet.filter'`
**New fields:** None

#### 2.1.1 Method: `_render`

```
_render(self, template_key, limit, search_domain=None, with_sample=False, **custom_template_data)
```

**Decision tree:**

```
template_key contains '.dynamic_filter_template_woow_' ?
├── NO  → delegate to super()._render(...)
└── YES → WoOW generic path:
    ├── self.ensure_one()
    ├── If website mismatch → return ''
    ├── Call self.with_context(woow_generic_mapping=True)._woow_prepare_values(limit, search_domain)
    ├── If with_sample and no records → self._prepare_sample(limit)
    ├── Render via ir.qweb._render(template_key, {records, is_sample, **custom_template_data})
    └── Return: list[str] — one HTML string per top-level child element
```

**Why needed:** Native `_render()` checks `self.model_name.replace('.', '_') not in template_key` which rejects WoOW generic templates that do not embed any model technical name.

**Code (complete):**

```python
def _render(self, template_key, limit, search_domain=None,
            with_sample=False, **custom_template_data):
    if '.dynamic_filter_template_woow_' not in template_key:
        return super()._render(
            template_key, limit, search_domain,
            with_sample=with_sample, **custom_template_data,
        )
    # -- WoOW generic path --
    self.ensure_one()
    if search_domain is None:
        search_domain = []
    if (self.website_id
            and self.env['website'].get_current_website() != self.website_id):
        return ''
    records = self.with_context(
        woow_generic_mapping=True,
    )._woow_prepare_values(limit=limit, search_domain=search_domain)
    is_sample = with_sample and not records
    if is_sample:
        records = self._prepare_sample(limit)
    content = self.env['ir.qweb'].with_context(
        inherit_branding=False,
    )._render(template_key, dict(
        records=records,
        is_sample=is_sample,
        **custom_template_data,
    ))
    return [
        etree.tostring(el, encoding='unicode', method='html')
        for el in lxml_html.fromstring(
            '<root>%s</root>' % str(content)
        ).getchildren()
    ]
```

#### 2.1.2 Method: `_woow_prepare_values`

```
_woow_prepare_values(self, limit=None, search_domain=None) → list[dict]
```

**Logic:**
1. `self.ensure_one()`
2. `max_limit = max(self.limit, 16)` -- floor of 16 records
3. `limit = min(limit, max_limit)` if limit given, else `max_limit`
4. If no `self.filter_id` → return `[]`
5. Get domain from `self.filter_id.sudo()._get_eval_domain()`
6. If model has `is_published` field → AND with `[('is_published', '=', True)]`
7. If `search_domain` → AND with search_domain
8. Parse `filter_id.context` and `filter_id.sort` via `literal_eval`
9. `self.env[model].sudo().search(domain, order=..., limit=limit)`
10. Return `self._filter_records_to_values(records)`

**Key difference from native `_prepare_values`:** Keeps `.sudo()` throughout instead of calling `.sudo(False)`. This allows public website pages to read models like `res.partner` that have no public ACL rules.

**Code (complete):**

```python
def _woow_prepare_values(self, limit=None, search_domain=None):
    self.ensure_one()
    max_limit = max(self.limit, 16)
    limit = limit and min(limit, max_limit) or max_limit
    if not self.filter_id:
        return []
    filter_sudo = self.filter_id.sudo()
    domain = filter_sudo._get_eval_domain()
    if 'is_published' in self.env[filter_sudo.model_id]:
        domain = expression.AND([
            domain, [('is_published', '=', True)],
        ])
    if search_domain:
        domain = expression.AND([domain, search_domain])
    ctx = literal_eval(filter_sudo.context) if filter_sudo.context else {}
    sort = literal_eval(filter_sudo.sort) if filter_sudo.sort else []
    records = self.env[filter_sudo.model_id].sudo().with_context(
        **ctx,
    ).search(
        domain,
        order=','.join(sort) or None,
        limit=limit,
    )
    return self._filter_records_to_values(records)
```

#### 2.1.3 Method: `_filter_records_to_values`

```
_filter_records_to_values(self, records, is_sample=False) → list[dict]
```

**Decision tree:**

```
context has woow_generic_mapping=True ?
├── NO  → delegate to super()._filter_records_to_values(records, is_sample)
└── YES → Generic mapping:
    For each record:
    ├── Parse field_names (comma-separated from self.field_names)
    ├── For each field_spec (strip :widget suffix):
    │   ├── field type is binary/image → data['image'] = '/web/image/{model}/{id}/{field}'
    │   │   └── (if is_sample → data['image'] = '/web/image')
    │   └── other field type → data['field_{N}'] = value (N increments)
    │       └── relational field → use .display_name
    ├── data['call_to_action_url'] = record.website_url or '#'
    ├── data['display_name'] = record.display_name
    └── data['_record'] = record
```

**Field mapping truth table:**

| Field spec | field_meta.type | Output key | Value |
|-----------|----------------|------------|-------|
| `name` | char | `field_0` | `record.name` |
| `email` | char | `field_1` | `record.email` |
| `city` | char | `field_2` | `record.city` |
| `image_128` | binary | `image` | `/web/image/res.partner/{id}/image_128` |
| `company_id` | many2one | `field_N` | `record.company_id.display_name` |
| (always set) | -- | `call_to_action_url` | `record.website_url` or `'#'` |
| (always set) | -- | `display_name` | `record.display_name` |
| (always set) | -- | `_record` | raw record reference |

**Code (complete):**

```python
def _filter_records_to_values(self, records, is_sample=False):
    if not self.env.context.get('woow_generic_mapping'):
        return super()._filter_records_to_values(records, is_sample=is_sample)
    values = []
    field_list = [
        f.strip()
        for f in (self.field_names or '').split(',')
        if f.strip()
    ]
    for record in records:
        data = {'_record': record}
        field_idx = 0
        for field_spec in field_list:
            raw_name = field_spec.split(':')[0]  # strip :widget suffix
            field_meta = record._fields.get(raw_name)
            if not field_meta:
                continue
            if field_meta.type in ('binary', 'image'):
                if is_sample:
                    data['image'] = '/web/image'
                else:
                    data['image'] = (
                        f'/web/image/{record._name}/{record.id}/{raw_name}'
                    )
            else:
                val = record[raw_name]
                if hasattr(val, 'display_name'):
                    val = val.display_name
                data[f'field_{field_idx}'] = val
                field_idx += 1
        data['call_to_action_url'] = getattr(record, 'website_url', '#')
        data['display_name'] = record.display_name
        values.append(data)
    return values
```

---

## 3. SECURITY ARCHITECTURE

### 3.1 Authentication Matrix

| Route | auth | Typical caller | Reason |
|-------|------|---------------|--------|
| `/woow_snippet/available_models` | `user` | Website editor (CUSTOMIZE panel) | Only logged-in editors should list available models |
| `/woow_snippet/model_fields` | `user` | Website editor (CUSTOMIZE panel) | Only logged-in editors should introspect field metadata |
| `/woow_snippet/stat` | `public` | Frontend widget (anonymous visitors) | Stat cards render on public pages |
| `/woow_snippet/chart` | `public` | Frontend widget (anonymous visitors) | Charts render on public pages |
| `/woow_snippet/data_table` | `public` | Frontend widget (anonymous visitors) | Data tables render on public pages |

All public routes have `readonly=True`.

### 3.2 Model Whitelist

The controller defines `_DEFAULT_ALLOWED_MODELS` (28 models):

```
res.partner          res.company          res.users
product.template     product.product      sale.order
sale.order.line      purchase.order       purchase.order.line
account.move         account.move.line    stock.picking
stock.move           project.project      project.task
hr.employee          hr.department        crm.lead
helpdesk.ticket      event.event          event.registration
survey.survey        survey.user_input    fleet.vehicle
maintenance.request  lunch.order          website.page
blog.post
```

**Extension point:** Override `_get_allowed_models()` on a custom controller to add models.

**Validation:** `_validate_model(model_name)` raises `ValueError` if model is not in whitelist OR not in `request.env` (i.e., the module providing that model is not installed).

### 3.3 Domain Validation

The `_safe_domain(domain_str)` function:

| Input | Output |
|-------|--------|
| `None`, `''`, `'[]'` | `[]` |
| Valid domain string, e.g. `"[('is_company','=',True)]"` | Parsed list of tuples |
| Invalid/malicious string | `[]` (logged as warning) |

Uses `odoo.tools.safe_eval.safe_eval` with restricted globals: `{'True': True, 'False': False, 'None': None}`.

### 3.4 Data Access Pattern

All public data endpoints use `.sudo()` on the target model. Access control is enforced by the model whitelist, not by Odoo ACL rules. This is a deliberate design choice because public website visitors do not have read access to most models (e.g., `res.partner`, `sale.order`).

---

## 4. CONTROLLER API REFERENCE

**File:** `controllers/main.py`
**Class:** `WoowSnippetController(http.Controller)`

### 4.1 Editor Endpoints (auth=user)

#### 4.1.1 GET Available Models

| Property | Value |
|----------|-------|
| Route | `/woow_snippet/available_models` |
| Type | `json` |
| Auth | `user` |
| Website | `True` |
| Parameters | None |

**Return value:**

```json
[
  {"model": "res.partner", "name": "Contact"},
  {"model": "sale.order", "name": "Sales Order"}
]
```

Returns only models that (a) are in the whitelist AND (b) exist in `request.env` (module installed). Sorted alphabetically by model technical name. Falls back to `model_name` if `_description` is unavailable.

#### 4.1.2 GET Model Fields

| Property | Value |
|----------|-------|
| Route | `/woow_snippet/model_fields` |
| Type | `json` |
| Auth | `user` |
| Website | `True` |

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `model_name` | str | Yes | Technical model name (e.g., `res.partner`) |

**Return value:**

```json
[
  {"name": "name", "string": "Name", "type": "char"},
  {"name": "email", "string": "Email", "type": "char"},
  {"name": "amount_total", "string": "Total", "type": "monetary"}
]
```

**Excluded field types:** `one2many`, `binary`, `serialized`, `properties`, `properties_definition`
**Excluded fields:** Fields starting with `_` and non-stored (computed without store) fields.

**Errors:** `ValueError` if model not in whitelist or not installed.

### 4.2 Public Data Endpoints (auth=public)

#### 4.2.1 Stat Card Data

| Property | Value |
|----------|-------|
| Route | `/woow_snippet/stat` |
| Type | `json` |
| Auth | `public` |
| Website | `True` |
| Readonly | `True` |

**Parameters:**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `model_name` | str | (required) | Technical model name |
| `operation` | str | `'count'` | One of: `count`, `sum`, `avg`, `min`, `max`, `count_distinct` |
| `field_name` | str | `''` | Field to aggregate (required for sum/avg/min/max/count_distinct) |
| `group_by` | str | `''` | Field to group by for breakdown |
| `domain` | str | `'[]'` | Domain filter as string |
| `sub_type` | str | `'default'` | One of: `default`, `progress`, `trend`, `threshold` |
| `target_value` | float | `100` | Target for progress/threshold |
| `threshold_warning` | float | `50` | Warning threshold percent |
| `threshold_danger` | float | `25` | Danger threshold percent |
| `previous_value` | float | `0` | Previous value for trend delta |

**Operation logic:**

| Operation | field_name | Implementation |
|-----------|-----------|---------------|
| `count` | (ignored) | `Model.search_count(domain)` |
| `count_distinct` | required | `len(Model.read_group(domain, [field], [field]))` |
| `sum` | required | `Model.read_group(domain, [field], [])[0][field]` |
| `avg` | required | `read_group_result[field] / __count` |
| `min` | required | `Model.search(domain, order='{field} asc', limit=1)[field]` |
| `max` | required | `Model.search(domain, order='{field} desc', limit=1)[field]` |
| any | empty | Falls back to `search_count(domain)` |

**Return value schema:**

```json
{
  "value": 42,
  "sub_type": "default",
  "breakdown": [
    {"label": "Category A", "value": 10},
    {"label": "Category B", "value": 32}
  ]
}
```

**Additional fields by sub_type:**

| sub_type | Additional fields | Computation |
|----------|------------------|-------------|
| `default` | (none) | -- |
| `progress` | `target`, `percent` | `percent = round(value / target * 100, 1)` |
| `trend` | `delta`, `delta_percent` | `delta = value - previous_value`; `delta_percent = round(delta / previous_value * 100, 1)` |
| `threshold` | `target`, `percent`, `status` | `status` = `'success'` if pct >= warning, `'warning'` if pct >= danger, `'danger'` otherwise |

**Threshold status truth table:**

| percent >= threshold_warning | percent >= threshold_danger | status |
|------------------------------|----------------------------|--------|
| true | true | `success` |
| false | true | `warning` |
| false | false | `danger` |

#### 4.2.2 Chart Data

| Property | Value |
|----------|-------|
| Route | `/woow_snippet/chart` |
| Type | `json` |
| Auth | `public` |
| Website | `True` |
| Readonly | `True` |

**Parameters:**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `model_name` | str | (required) | Technical model name |
| `chart_type` | str | `'bar'` | Chart type identifier (see Section 7) |
| `label_field` | str | `''` | Field for X-axis / labels (required) |
| `value_field` | str | `''` | Field for Y-axis / values (required) |
| `domain` | str | `'[]'` | Domain filter as string |
| `gauge_max` | float | `100` | Maximum value for gauge chart |
| `series_field` | str | `''` | Field for multi-series grouping |

**Count detection:** If `value_field` is `'id'` or `'__count'`, the endpoint uses record count per group instead of field aggregation. The count key in `read_group` results follows the format `{groupby_field}_count`.

**Return value schema (single-series):**

```json
{
  "labels": ["Draft", "Sent", "Done"],
  "datasets": [{"label": "amount_total", "data": [1000, 2500, 8000]}],
  "chart_type": "bar",
  "gauge_max": 100
}
```

**Return value schema (multi-series with series_field):**

```json
{
  "labels": ["Jan", "Feb", "Mar"],
  "datasets": [
    {"label": "Category A", "data": [10, 20, 30]},
    {"label": "Category B", "data": [5, 15, 25]}
  ],
  "chart_type": "bar",
  "gauge_max": 100
}
```

**Multi-series logic:** When `series_field` is set, `read_group` is called with `groupby=[label_field, series_field]` and `lazy=False`. Results are pivoted into a label-set and series-map. Missing label/series combinations default to `0`.

**Empty input handling:** If `label_field` or `value_field` is empty, returns `{'labels': [], 'datasets': []}`.

**Label extraction for relational fields:** Many2one results from `read_group` come as `[id, name]` tuples; the endpoint extracts index `[1]` (display name).

#### 4.2.3 Data Table Data

| Property | Value |
|----------|-------|
| Route | `/woow_snippet/data_table` |
| Type | `json` |
| Auth | `public` |
| Website | `True` |
| Readonly | `True` |

**Parameters:**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `model_name` | str | (required) | Technical model name |
| `field_names` | str | `''` | Comma-separated field names |
| `domain` | str | `'[]'` | Domain filter as string |
| `offset` | int | `0` | Pagination offset (clamped to >= 0) |
| `limit` | int | `25` | Page size (clamped to 1-100) |
| `sort_field` | str | `''` | Field to sort by (must be in valid_fields) |
| `sort_order` | str | `'asc'` | Sort direction: `asc` or `desc` |
| `search_term` | str | `''` | Free-text search term |

**Return value schema:**

```json
{
  "columns": [
    {"name": "name", "string": "Name", "type": "char"},
    {"name": "email", "string": "Email", "type": "char"}
  ],
  "rows": [
    {"id": 1, "name": "Alice", "email": "alice@example.com"},
    {"id": 2, "name": "Bob", "email": "bob@example.com"}
  ],
  "total": 150,
  "offset": 0,
  "limit": 25
}
```

**Search logic:** OR-combined `ilike` across all `char`, `text`, and `html` fields in the requested field list.

**Sort validation:** `sort_field` must be in the validated `valid_fields` list; `sort_order` must be in `{'asc', 'desc'}`.

**Value rendering for relational fields:**
- `many2one` → `.display_name`
- `many2many` / `one2many` → `', '.join(val.mapped('display_name'))`

**Empty input handling:** If `field_names` is empty or none resolve to valid fields, returns `{'columns': [], 'rows': [], 'total': 0}`.

---

## 5. FRONTEND WIDGET ARCHITECTURE

### 5.1 Widget Registry

| Registry Key | File | Bundle | Base Class |
|-------------|------|--------|-----------|
| `publicWidget.registry.s_woow_dynamic_content` | `s_woow_dynamic_content/000.js` | `web.assets_frontend` | `DynamicSnippet` (from `@website/snippets/s_dynamic_snippet/000`) |
| `publicWidget.registry.s_woow_stat` | `s_woow_stat/000.js` | `web.assets_frontend` | `publicWidget.Widget` |
| `publicWidget.registry.s_woow_chart` | `s_woow_chart/000.js` | `web.assets_frontend` | `publicWidget.Widget` |
| `publicWidget.registry.s_woow_data_table` | `s_woow_data_table/000.js` | `web.assets_frontend` | `publicWidget.Widget` |

### 5.2 Widget: s_woow_dynamic_content (000.js)

| Property | Value |
|----------|-------|
| Selector | `.s_woow_dynamic_content` |
| Extends | `DynamicSnippet` from `@website/snippets/s_dynamic_snippet/000` |
| disabledInEditableMode | inherited (true by default from DynamicSnippet) |

**Overridden methods:**

**`_getSearchDomain()`** -- Builds additional search domain tuples based on `data-filter-mode`:

| data-filter-mode | Source | Key prefix | Field name derivation | Value parsing |
|-----------------|--------|------------|----------------------|--------------|
| `by_page_context` | Closest ancestor `[data-woow-ctx-model]` dataset | `woowCtx` | camelCase → snake_case (e.g., `woowCtxPartnerId` → `partner_id`) | `parseInt`, falls back to string |
| `by_url_param` | `window.location.search` URL params | `woow_` | Strip prefix (e.g., `woow_partner_id` → `partner_id`) | `parseInt`, falls back to string |

**`_getRpcParameters()`** -- Adds `{with_context: {woow_generic_mapping: true}}` to the RPC parameters, activating the generic field mapping in `_filter_records_to_values`.

### 5.3 Widget: s_woow_stat (000.js)

| Property | Value |
|----------|-------|
| Selector | `.s_woow_stat` |
| Extends | `publicWidget.Widget` |
| disabledInEditableMode | `false` (renders in editor) |
| RPC endpoint | `/woow_snippet/stat` |

**Data attributes read:**

| data-* attribute | JS key | Passed as RPC param | Default |
|-----------------|--------|-------------------|---------|
| `data-model-name` | `modelName` | `model_name` | `''` |
| `data-operation` | `operation` | `operation` | `'count'` |
| `data-stat-field` | `statField` | `field_name` | `''` |
| `data-group-by` | `groupBy` | `group_by` | `''` |
| `data-domain` | `domain` | `domain` | `'[]'` |
| `data-sub-type` | `subType` | `sub_type` | `'default'` |
| `data-target-value` | `targetValue` | `target_value` | `100` |
| `data-threshold-warning` | `thresholdWarning` | `threshold_warning` | `50` |
| `data-threshold-danger` | `thresholdDanger` | `threshold_danger` | `25` |
| `data-previous-value` | `previousValue` | `previous_value` | `0` |

**Rendering sub-types:**

| sub_type | Visual output |
|----------|--------------|
| `default` | Large number + label |
| `progress` | Large number + label + Bootstrap progress bar + "X% of target" |
| `trend` | Large number + label + delta arrow (up=green, down=red) + delta percent |
| `threshold` | Large number + label + colored progress bar (success/warning/danger) |

**Breakdown rendering:** If `result.breakdown` is non-empty, appends a list of `{label, value}` rows below the main stat.

**`_formatNumber(num)`:** Locale-aware formatting. Integers get `.toLocaleString()`. Floats get max 2 decimal places.

### 5.4 Widget: s_woow_chart (000.js)

| Property | Value |
|----------|-------|
| Selector | `.s_woow_chart` |
| Extends | `publicWidget.Widget` |
| disabledInEditableMode | `false` (renders in editor) |
| RPC endpoint | `/woow_snippet/chart` |
| External dependency | Chart.js loaded via `loadJS('/web/static/lib/Chart/Chart.js')` |

**Data attributes read:**

| data-* attribute | JS key | Passed as RPC param | Default |
|-----------------|--------|-------------------|---------|
| `data-model-name` | `modelName` | `model_name` | `''` |
| `data-chart-type` | `chartType` | `chart_type` | `'bar'` |
| `data-label-field` | `labelField` | `label_field` | `''` |
| `data-value-field` | `valueField` | `value_field` | `''` |
| `data-domain` | `domain` | `domain` | `'[]'` |
| `data-gauge-max` | `gaugeMax` | `gauge_max` | `100` |
| `data-series-field` | `seriesField` | `series_field` | `''` |

**Color palette (15 colors):**

```
#3B82F6, #10B981, #F59E0B, #EF4444, #8B5CF6,
#EC4899, #06B6D4, #84CC16, #F97316, #6366F1,
#14B8A6, #E11D48, #0EA5E9, #A855F7, #22C55E
```

**Chart config routing:**

```
chartType === 'gauge'  → _buildGaugeConfig(result)
chartType === 'funnel' → _buildFunnelConfig(result)
all others             → _buildStandardConfig(result, chartType)
```

**Lifecycle:** `destroy()` calls `this._chartInstance.destroy()` to properly clean up the Chart.js instance.

See Section 7 for complete chart type reference.

### 5.5 Widget: s_woow_data_table (000.js)

| Property | Value |
|----------|-------|
| Selector | `.s_woow_data_table` |
| Extends | `publicWidget.Widget` |
| disabledInEditableMode | `false` (renders in editor) |
| RPC endpoint | `/woow_snippet/data_table` |

**Data attributes read:**

| data-* attribute | JS key | Passed as RPC param | Default |
|-----------------|--------|-------------------|---------|
| `data-model-name` | `modelName` | `model_name` | `''` |
| `data-field-names` | `fieldNames` | `field_names` | `''` |
| `data-domain` | `domain` | `domain` | `'[]'` |
| `data-page-size` | `pageSize` | `limit` | `25` |
| `data-searchable` | `searchable` | (client-side toggle) | `'1'` |
| `data-sortable` | `sortable` | (client-side toggle) | `'1'` |

**Client-side state:**

| Property | Initial | Updated by |
|----------|---------|-----------|
| `_currentOffset` | `0` | `_onPageClick`, `_onSortClick`, `_onSearchInput` |
| `_sortField` | `''` | `_onSortClick` |
| `_sortOrder` | `'asc'` | `_onSortClick` (toggles asc/desc on same field) |
| `_searchTerm` | `''` | `_onSearchInput` (debounced 300ms) |

**Events:**

| Event | Selector | Handler |
|-------|----------|---------|
| `click` | `.woow_dt_page` | `_onPageClick` — reads `data-offset` from clicked pagination link |
| `click` | `.woow_dt_sort` | `_onSortClick` — reads `data-field` from column header |
| `input` | `.woow_dt_search` | `_onSearchInput` — debounced 300ms, resets offset to 0 |

**Pagination:** Renders up to 10 page links. If total pages > 10, appends `"... (N pages)"` indicator.

**XSS prevention:** `_escapeHtml(str)` replaces `&`, `<`, `>`, `"` with HTML entities.

### 5.6 Editor Options Registry

| Registry Key | File | Bundle | Base Class |
|-------------|------|--------|-----------|
| `options.registry.woow_dynamic_content` | `s_woow_dynamic_content/options.js` | `website.assets_wysiwyg` | `dynamicSnippetOptions` (from `@website/snippets/s_dynamic_snippet/options`) |
| `options.registry.woow_stat` | `s_woow_stat/options.js` | `website.assets_wysiwyg` | `options.Class` |
| `options.registry.woow_chart` | `s_woow_chart/options.js` | `website.assets_wysiwyg` | `options.Class` |
| `options.registry.woow_data_table` | `s_woow_data_table/options.js` | `website.assets_wysiwyg` | `options.Class` |

**Common pattern for stat/chart/data_table options:**
1. `willStart()` → fetch `/woow_snippet/available_models` → store as `this.availableModels`
2. `_renderCustomXML(uiFragment)` → populate `we-select` elements with `we-button` children
3. `selectDataAttribute()` → on `modelName` change, fetch `/woow_snippet/model_fields` → store as `this.modelFields` → `_rerenderXML()` + `_refreshPublicWidgets()`
4. Other attribute changes → `_refreshPublicWidgets()` only

**Dynamic Content options:** Sets `modelNameFilter: undefined` to remove the native single-model restriction, allowing all `website.snippet.filter` records regardless of model.

**Field type filtering per option class:**

| Option class | field_opt types | group_by_opt types | label_field_opt types | value_field_opt types | series_field_opt types |
|-------------|----------------|-------------------|---------------------|---------------------|----------------------|
| `woow_stat` | integer, float, monetary | selection, many2one, char, date, datetime, boolean | -- | -- | -- |
| `woow_chart` | -- | -- | char, selection, many2one, date, datetime, boolean | integer, float, monetary | char, selection, many2one, boolean |
| `woow_data_table` | -- (uses text input) | -- | -- | -- | -- |

---

## 6. VIEW ARCHITECTURE (XML Templates)

### 6.1 Snippet Registration (snippets.xml)

**Template ID:** `woow_snippet_builder.snippets`
**Inherits:** `website.snippets`
**XPath:** `//t[@id='installed_snippets_hook']` position `after`
**Effect:** Adds a `"WoOW Dynamic"` snippet group tab after native installed snippets.

**Template ID:** `woow_snippet_builder.woow_snippets_list`
**Inherits:** `website.snippets`
**XPath:** `//t[@snippet-group='woow_dynamic']` position `after`
**Effect:** Registers 4 snippet blocks into the WoOW Dynamic group.

| Snippet | t-snippet ref | Group | Keywords |
|---------|-------------|-------|----------|
| Dynamic Content | `woow_snippet_builder.s_woow_dynamic_content` | `woow_dynamic` | woow, dynamic, content, data, records, list, card |
| Stat Card | `woow_snippet_builder.s_woow_stat` | `woow_dynamic` | woow, stat, card, counter, kpi, metric, number |
| Chart | `woow_snippet_builder.s_woow_chart` | `woow_dynamic` | woow, chart, graph, bar, line, pie, doughnut, radar |
| Data Table | `woow_snippet_builder.s_woow_data_table` | `woow_dynamic` | woow, table, data, grid, list, paginated |

### 6.2 Snippet Bodies and CUSTOMIZE Panel Options

#### 6.2.1 s_woow_dynamic_content

**Body template ID:** `woow_snippet_builder.s_woow_dynamic_content`
**Mechanism:** Calls `website.s_dynamic_snippet_template` with `snippet_name='s_woow_dynamic_content'`

**Options template ID:** `woow_snippet_builder.s_woow_dynamic_content_options`
**Inherits:** `website.snippet_options`
**Mechanism:** Calls `website.s_dynamic_snippet_options_template` with `snippet_name='woow_dynamic_content'`, `snippet_selector='.s_woow_dynamic_content'`

#### 6.2.2 s_woow_stat

**Body template ID:** `woow_snippet_builder.s_woow_stat`
**Root element:** `section.s_woow_stat.pt32.pb32`
**Content container:** `div.woow_stat_content`

**Default data-* attributes on body:**

| Attribute | Default |
|-----------|---------|
| `data-model-name` | `""` |
| `data-operation` | `"count"` |
| `data-stat-field` | `""` |
| `data-group-by` | `""` |
| `data-domain` | `"[]"` |
| `data-sub-type` | `"default"` |
| `data-target-value` | `"100"` |
| `data-threshold-warning` | `"50"` |
| `data-threshold-danger` | `"25"` |
| `data-previous-value` | `"0"` |

**Options template ID:** `woow_snippet_builder.s_woow_stat_options`
**Inherits:** `website.snippet_options`
**data-js:** `woow_stat`
**data-selector:** `.s_woow_stat`

**CUSTOMIZE panel controls:**

| Control | Type | data-name | data-attribute-name | Static values |
|---------|------|-----------|-------------------|--------------|
| Model | we-select | `model_opt` | `modelName` | (dynamic from RPC) |
| Operation | we-select | -- | `operation` | count, sum, avg, min, max, count_distinct |
| Field | we-select | `field_opt` | `statField` | (dynamic from RPC, numeric only) |
| Group By | we-select | `group_by_opt` | `groupBy` | (dynamic from RPC) |
| Style | we-select | -- | `subType` | default, progress, trend, threshold |
| Target Value | we-input | -- | `targetValue` | -- |
| Previous Value | we-input | -- | `previousValue` | -- |
| Domain | we-input | -- | `domain` | -- |

#### 6.2.3 s_woow_chart

**Body template ID:** `woow_snippet_builder.s_woow_chart`
**Root element:** `section.s_woow_chart.pt32.pb32`
**Content container:** `div.woow_chart_content` (height: 400px)

**Default data-* attributes on body:**

| Attribute | Default |
|-----------|---------|
| `data-model-name` | `""` |
| `data-chart-type` | `"bar"` |
| `data-label-field` | `""` |
| `data-value-field` | `""` |
| `data-domain` | `"[]"` |
| `data-gauge-max` | `"100"` |
| `data-series-field` | `""` |

**Options template ID:** `woow_snippet_builder.s_woow_chart_options`
**Inherits:** `website.snippet_options`
**data-js:** `woow_chart`
**data-selector:** `.s_woow_chart`

**CUSTOMIZE panel controls:**

| Control | Type | data-name | data-attribute-name | Static values |
|---------|------|-----------|-------------------|--------------|
| Model | we-select | `model_opt` | `modelName` | (dynamic from RPC) |
| Chart Type | we-select | -- | `chartType` | bar, line, pie, doughnut, radar, polarArea, bar_horizontal, bar_stacked, gauge, funnel |
| Label Field | we-select | `label_field_opt` | `labelField` | (dynamic from RPC) |
| Value Field | we-select | `value_field_opt` | `valueField` | (dynamic from RPC) |
| Series Field | we-select | `series_field_opt` | `seriesField` | (dynamic from RPC) |
| Gauge Max | we-input | -- | `gaugeMax` | -- |
| Domain | we-input | -- | `domain` | -- |

#### 6.2.4 s_woow_data_table

**Body template ID:** `woow_snippet_builder.s_woow_data_table`
**Root element:** `section.s_woow_data_table.pt32.pb32`
**Content container:** `div.woow_data_table_content`

**Default data-* attributes on body:**

| Attribute | Default |
|-----------|---------|
| `data-model-name` | `""` |
| `data-field-names` | `""` |
| `data-domain` | `"[]"` |
| `data-page-size` | `"25"` |
| `data-searchable` | `"1"` |
| `data-sortable` | `"1"` |

**Options template ID:** `woow_snippet_builder.s_woow_data_table_options`
**Inherits:** `website.snippet_options`
**data-js:** `woow_data_table`
**data-selector:** `.s_woow_data_table`

**CUSTOMIZE panel controls:**

| Control | Type | data-name | data-attribute-name | Static values |
|---------|------|-----------|-------------------|--------------|
| Model | we-select | `model_opt` | `modelName` | (dynamic from RPC) |
| Fields | we-input | `fields_opt` | `fieldNames` | -- (placeholder: `name,email,city`) |
| Page Size | we-select | -- | `pageSize` | 10, 25, 50, 100 |
| Searchable | we-select | -- | `searchable` | 1 (Yes), 0 (No) |
| Sortable | we-select | -- | `sortable` | 1 (Yes), 0 (No) |
| Domain | we-input | -- | `domain` | -- |

### 6.3 QWeb Dynamic Filter Templates

**File:** `data/woow_dynamic_filter_templates.xml`

All templates use generic keys (`field_0`, `field_1`, `field_2`, `image`) and iterate over `records` (list of dicts from `_filter_records_to_values`).

| Template ID | Name | data-number-of-elements | Layout description |
|-------------|------|------------------------|-------------------|
| `woow_snippet_builder.dynamic_filter_template_woow_card` | WoOW Card | `4` | Card with cover image (180px), title (field_0), subtitle (field_1), body text (field_2) |
| `woow_snippet_builder.dynamic_filter_template_woow_list` | WoOW List | `1` | Row with 36px circular avatar, 3 inline text spans |
| `woow_snippet_builder.dynamic_filter_template_woow_hero` | WoOW Hero Card | `3` | Card with 200px cover image, gradient overlay with title, body subtitle |
| `woow_snippet_builder.dynamic_filter_template_woow_compact` | WoOW Compact | `1` | Row with 40px circular avatar, stacked title + subtitle |
| `woow_snippet_builder.dynamic_filter_template_woow_table` | WoOW Table | `1` | 3-column row (col-4 each), field_2 hidden on mobile (d-none d-md-block) |
| `woow_snippet_builder.dynamic_filter_template_woow_timeline` | WoOW Timeline | `1` | Numbered circle (data_index + 1) + stacked text with border-bottom |

All templates set `data-number-of-elements-sm="1"` and share the same thumbnail SVG.

### 6.4 Demo Data

**File:** `data/woow_snippet_filter_data.xml` (noupdate="1")

| XML ID | Model | Key fields |
|--------|-------|-----------|
| `woow_snippet_builder.woow_filter_partners` | `ir.filters` | name="All Contacts", model_id=base.model_res_partner, domain=[('is_company','=',False)], sort=["name asc"] |
| `woow_snippet_builder.woow_snippet_filter_partners` | `website.snippet.filter` | name="Contacts", filter_id=woow_filter_partners, field_names=name,email,city,image_128, limit=16 |
| `woow_snippet_builder.woow_filter_companies` | `ir.filters` | name="All Companies", model_id=base.model_res_partner, domain=[('is_company','=',True)], sort=["name asc"] |
| `woow_snippet_builder.woow_snippet_filter_companies` | `website.snippet.filter` | name="Companies", filter_id=woow_filter_companies, field_names=name,email,city,image_128, limit=16 |

---

## 7. CHART TYPE REFERENCE

### 7.1 Chart Type Table

| chart_type value | Chart.js type | Config builder | Notes |
|-----------------|--------------|----------------|-------|
| `bar` | `bar` | `_buildStandardConfig` | Vertical bars |
| `line` | `line` | `_buildStandardConfig` | `fill: false`, `tension: 0.3` |
| `pie` | `pie` | `_buildStandardConfig` | Per-segment colors from COLORS palette |
| `doughnut` | `doughnut` | `_buildStandardConfig` | Per-segment colors from COLORS palette |
| `radar` | `radar` | `_buildStandardConfig` | Standard radar chart |
| `polarArea` | `polarArea` | `_buildStandardConfig` | Per-segment colors from COLORS palette |
| `bar_horizontal` | `bar` | `_buildStandardConfig` | `indexAxis: 'y'` |
| `bar_stacked` | `bar` | `_buildStandardConfig` | `scales.x.stacked: true`, `scales.y.stacked: true` |
| `gauge` | `doughnut` | `_buildGaugeConfig` | `circumference: 180`, `rotation: -90`, `cutout: '75%'`, custom `afterDraw` plugin for center label |
| `funnel` | `bar` | `_buildFunnelConfig` | Horizontal bar, data sorted descending by value |

### 7.2 Standard Chart Config Details

**Pie-family charts** (`pie`, `doughnut`, `polarArea`):
- Each data point gets a different color from the COLORS palette
- `backgroundColor` is an array of colors mapped per data point
- Legend is always displayed

**Non-pie charts** (`bar`, `line`, `radar`, `bar_horizontal`, `bar_stacked`):
- Each dataset gets a single color (with `99` hex alpha for backgroundColor)
- `borderWidth: 2`
- Legend displayed only if multiple datasets

**Line-specific:** `fill: false`, `tension: 0.3`

**All standard charts:** `responsive: true`, `maintainAspectRatio: false`

### 7.3 Gauge Config Details

```javascript
{
  type: 'doughnut',
  data: {
    datasets: [{
      data: [pct, 100 - pct],           // pct = min(value / max * 100, 100)
      backgroundColor: [COLORS[0], '#e5e7eb'],  // blue fill, gray remainder
      borderWidth: 0,
    }],
  },
  options: {
    circumference: 180,    // half-doughnut
    rotation: -90,         // start from left
    cutout: '75%',         // thick ring
    plugins: { legend: {display: false}, tooltip: {enabled: false} },
  },
  plugins: [{
    id: 'gaugeLabel',
    afterDraw(chart) {
      // Draws value (bold 28px) and "/ max" (14px gray) centered at bottom
    },
  }],
}
```

### 7.4 Funnel Config Details

- Sorts label/value pairs descending by value
- Renders as horizontal bar (`indexAxis: 'y'`)
- Per-bar colors from COLORS palette
- Legend hidden
- `scales.x.beginAtZero: true`

### 7.5 Chart Type Decision Tree

```
Need a gauge / speedometer display?
├── YES → gauge (requires gauge_max)
└── NO
    Need a funnel / pipeline visualization?
    ├── YES → funnel (auto-sorts descending)
    └── NO
        Categorical comparison?
        ├── YES
        │   Part-of-whole composition?
        │   ├── YES
        │   │   Want center hole? → doughnut
        │   │   No center hole? → pie
        │   │   Radial segments? → polarArea
        │   └── NO
        │       Multiple categories to compare?
        │       ├── Horizontal preferred? → bar_horizontal
        │       ├── Multiple stacked series? → bar_stacked
        │       └── Standard? → bar
        └── NO
            Trend over time?
            ├── YES → line
            └── NO
                Multi-axis comparison? → radar
```

---

## 8. COMMON QUERIES (FAQ for LLMs)

### Q: How to add a new snippet type?

1. Create `static/src/snippets/s_woow_<name>/000.js` (frontend widget)
2. Create `static/src/snippets/s_woow_<name>/options.js` (editor options)
3. Create `views/snippets/s_woow_<name>.xml` (body template + options template inheriting `website.snippet_options`)
4. Add a controller route if the snippet needs server data
5. Register in `views/snippets/snippets.xml` under the `woow_dynamic` group
6. Add JS files to `__manifest__.py` assets (`web.assets_frontend` for 000.js, `website.assets_wysiwyg` for options.js)
7. Add XML to `__manifest__.py` data list

### Q: How to add a new model to the whitelist?

Option A (modify this module): Add the model name to `_DEFAULT_ALLOWED_MODELS` set in `controllers/main.py`.

Option B (extend without modifying): Create a new controller inheriting `WoowSnippetController` and override `_get_allowed_models()`:

```python
class MyController(WoowSnippetController):
    def _get_allowed_models(self):
        return super()._get_allowed_models() | {'my.custom.model'}
```

### Q: How does the generic field mapping work?

1. `DynamicSnippet` JS widget sets `with_context: {woow_generic_mapping: true}` in RPC params
2. `website.snippet.filter._render()` detects `.dynamic_filter_template_woow_` in template_key
3. Calls `_woow_prepare_values()` which searches records with `.sudo()`
4. `_filter_records_to_values()` sees `woow_generic_mapping` in context
5. Maps fields positionally: first non-binary field → `field_0`, second → `field_1`, etc.
6. First binary/image field → `image` (as `/web/image/...` URL)
7. QWeb templates reference `field_0`, `field_1`, `field_2`, `image` -- same keys regardless of model

### Q: How does Dynamic Content rendering work end-to-end?

```
[Browser] DynamicSnippet.start()
  → _fetch() → RPC /website/snippet/filters
    → [Server] website.snippet.filter._render(template_key, limit, search_domain)
      → Detects '.dynamic_filter_template_woow_' in template_key
      → _woow_prepare_values(limit, search_domain)
        → filter_id.sudo()._get_eval_domain()
        → Model.sudo().search(domain, order, limit)
        → _filter_records_to_values(records)  [with woow_generic_mapping=True]
          → Returns [{field_0: ..., field_1: ..., image: ..., ...}, ...]
      → ir.qweb._render(template_key, {records: values})
      → Split HTML into list of element strings
    → [Server returns HTML fragments]
  → [Browser] Inserts HTML into DOM
```

### Q: What chart types are available and when to use each?

See Section 7.1 for the complete table and Section 7.5 for the decision tree.

### Q: How does domain filtering work?

Three domain sources are combined:

1. **Static domain** -- Set in CUSTOMIZE panel via `data-domain` attribute. Parsed by `_safe_domain()` on the server.
2. **Page context domain** (Dynamic Content only) -- When `data-filter-mode="by_page_context"`, reads `data-woow-ctx-*` attributes from ancestor elements. Example: `<div data-woow-ctx-model="res.partner" data-woow-ctx-company-id="1">` produces domain `[('company_id', '=', 1)]`.
3. **URL parameter domain** (Dynamic Content only) -- When `data-filter-mode="by_url_param"`, reads URL params prefixed with `woow_`. Example: `?woow_state=draft` produces domain `[('state', '=', 'draft')]`.

For Stat/Chart/Data Table, only the static domain (source 1) applies; filtering is done server-side in the controller.

### Q: How to configure multi-series charts?

Set `data-series-field` (via the "Series Field" dropdown in CUSTOMIZE panel) to a categorical field. The controller groups by both `label_field` and `series_field` using `read_group(..., [label_field, series_field], lazy=False)`. Each unique value of `series_field` becomes a separate dataset in the chart. Works with `bar`, `line`, `bar_stacked`, and `radar` chart types.

---

## 9. CODE ARCHITECTURE

### 9.1 File-by-File Description

| File | Purpose |
|------|---------|
| `__init__.py` | Imports `controllers` and `models` packages |
| `__manifest__.py` | Module metadata, dependencies, data files, asset declarations |
| `controllers/__init__.py` | Imports `main` |
| `controllers/main.py` | 5 JSON-RPC routes: 2 editor (auth=user) + 3 public (auth=public); model whitelist; domain parsing |
| `models/__init__.py` | Imports `website_snippet_filter` |
| `models/website_snippet_filter.py` | Inherits `website.snippet.filter`; overrides `_render`, `_filter_records_to_values`; adds `_woow_prepare_values` |
| `static/src/snippets/s_woow_dynamic_content/000.js` | Frontend widget extending DynamicSnippet; context/URL param filtering |
| `static/src/snippets/s_woow_dynamic_content/options.js` | Editor options; removes model filter restriction |
| `static/src/snippets/s_woow_stat/000.js` | Frontend widget for stat card; 4 sub-type renderers |
| `static/src/snippets/s_woow_stat/options.js` | Editor options; dynamic model/field/group-by selects |
| `static/src/snippets/s_woow_chart/000.js` | Frontend widget for charts; Chart.js integration; 3 config builders |
| `static/src/snippets/s_woow_chart/options.js` | Editor options; dynamic model/label/value/series field selects |
| `static/src/snippets/s_woow_data_table/000.js` | Frontend widget for data table; pagination, search, sort |
| `static/src/snippets/s_woow_data_table/options.js` | Editor options; dynamic model select; auto-populates first 5 fields |
| `data/woow_dynamic_filter_templates.xml` | 6 QWeb templates for Dynamic Content layouts |
| `data/woow_snippet_filter_data.xml` | Demo ir.filters + website.snippet.filter records (noupdate=1) |
| `views/snippets/snippets.xml` | Registers WoOW Dynamic group + 4 snippets in BLOCKS panel |
| `views/snippets/s_woow_dynamic_content.xml` | Dynamic Content body + CUSTOMIZE options |
| `views/snippets/s_woow_stat.xml` | Stat Card body + CUSTOMIZE options |
| `views/snippets/s_woow_chart.xml` | Chart body + CUSTOMIZE options |
| `views/snippets/s_woow_data_table.xml` | Data Table body + CUSTOMIZE options |
| `static/src/img/snippets_thumbs/s_woow_chart.svg` | Thumbnail for Chart snippet |
| `static/src/img/snippets_thumbs/s_woow_data_table.svg` | Thumbnail for Data Table snippet |
| `static/src/img/snippets_thumbs/s_woow_dynamic_content.svg` | Thumbnail for Dynamic Content snippet |
| `static/src/img/snippets_thumbs/s_woow_stat.svg` | Thumbnail for Stat Card snippet |

### 9.2 Import Chain

```
__init__.py
├── controllers/
│   ├── __init__.py
│   └── main.py
│       ├── odoo.http
│       ├── odoo.http.request
│       └── odoo.tools.safe_eval.safe_eval
└── models/
    ├── __init__.py
    └── website_snippet_filter.py
        ├── ast.literal_eval
        ├── lxml.etree
        ├── lxml.html
        ├── odoo.models
        └── odoo.osv.expression
```

**JavaScript import chain:**

```
s_woow_dynamic_content/000.js
├── @website/snippets/s_dynamic_snippet/000  (DynamicSnippet)
└── @web/legacy/js/public/public_widget

s_woow_dynamic_content/options.js
├── @website/snippets/s_dynamic_snippet/options  (dynamicSnippetOptions)
└── @web_editor/js/editor/snippets.options

s_woow_stat/000.js
├── @web/legacy/js/public/public_widget
└── @web/core/network/rpc

s_woow_stat/options.js
├── @web_editor/js/editor/snippets.options
└── @web/core/network/rpc

s_woow_chart/000.js
├── @web/legacy/js/public/public_widget
├── @web/core/network/rpc
└── @web/core/assets  (loadJS)

s_woow_chart/options.js
├── @web_editor/js/editor/snippets.options
└── @web/core/network/rpc

s_woow_data_table/000.js
├── @web/legacy/js/public/public_widget
└── @web/core/network/rpc

s_woow_data_table/options.js
├── @web_editor/js/editor/snippets.options
└── @web/core/network/rpc
```

### 9.3 Asset Bundle Loading Order

**`web.assets_frontend`** (loaded on every public page):

1. `woow_snippet_builder/static/src/snippets/s_woow_dynamic_content/000.js`
2. `woow_snippet_builder/static/src/snippets/s_woow_stat/000.js`
3. `woow_snippet_builder/static/src/snippets/s_woow_chart/000.js`
4. `woow_snippet_builder/static/src/snippets/s_woow_data_table/000.js`

**`website.assets_wysiwyg`** (loaded only in website editor):

1. `woow_snippet_builder/static/src/snippets/s_woow_dynamic_content/options.js`
2. `woow_snippet_builder/static/src/snippets/s_woow_stat/options.js`
3. `woow_snippet_builder/static/src/snippets/s_woow_chart/options.js`
4. `woow_snippet_builder/static/src/snippets/s_woow_data_table/options.js`

### 9.4 Data Loading Order (from __manifest__.py)

1. `data/woow_snippet_filter_data.xml` — demo ir.filters + website.snippet.filter records (noupdate=1)
2. `data/woow_dynamic_filter_templates.xml` — 6 QWeb templates
3. `views/snippets/snippets.xml` — snippet group + block registration
4. `views/snippets/s_woow_dynamic_content.xml` — body + options
5. `views/snippets/s_woow_stat.xml` — body + options
6. `views/snippets/s_woow_chart.xml` — body + options
7. `views/snippets/s_woow_data_table.xml` — body + options

---

## 10. DEPLOYMENT NOTES

### 10.1 Dependencies

Only `website` module is required. All other models in the whitelist (e.g., `sale.order`, `hr.employee`) are optional -- the controller checks `model_name not in request.env` and raises `ValueError` if the model's module is not installed.

### 10.2 Installation

```bash
# Install the module
./odoo-bin -d <database> -i woow_snippet_builder

# Update after code changes
./odoo-bin -d <database> -u woow_snippet_builder
```

### 10.3 Chart.js Dependency

Chart.js is loaded from Odoo's bundled library at `/web/static/lib/Chart/Chart.js`. No external CDN calls are made. The `s_woow_chart` widget loads it lazily via `loadJS()` only when a chart needs to render.

### 10.4 Public Access

All public endpoints use `.sudo()` to bypass ACL. The model whitelist (`_DEFAULT_ALLOWED_MODELS`) is the security boundary. If a model is removed from the whitelist, its data becomes inaccessible through all snippet endpoints.

---

## 11. QUICK REFERENCE CHEAT SHEET

### 11.1 All XML IDs

**QWeb Templates (ir.ui.view):**

| XML ID | Type |
|--------|------|
| `woow_snippet_builder.snippets` | Inherits `website.snippets` (group registration) |
| `woow_snippet_builder.woow_snippets_list` | Inherits `website.snippets` (block registration) |
| `woow_snippet_builder.s_woow_dynamic_content` | Snippet body template |
| `woow_snippet_builder.s_woow_dynamic_content_options` | Inherits `website.snippet_options` |
| `woow_snippet_builder.s_woow_stat` | Snippet body template |
| `woow_snippet_builder.s_woow_stat_options` | Inherits `website.snippet_options` |
| `woow_snippet_builder.s_woow_chart` | Snippet body template |
| `woow_snippet_builder.s_woow_chart_options` | Inherits `website.snippet_options` |
| `woow_snippet_builder.s_woow_data_table` | Snippet body template |
| `woow_snippet_builder.s_woow_data_table_options` | Inherits `website.snippet_options` |
| `woow_snippet_builder.dynamic_filter_template_woow_card` | QWeb dynamic filter template |
| `woow_snippet_builder.dynamic_filter_template_woow_list` | QWeb dynamic filter template |
| `woow_snippet_builder.dynamic_filter_template_woow_hero` | QWeb dynamic filter template |
| `woow_snippet_builder.dynamic_filter_template_woow_compact` | QWeb dynamic filter template |
| `woow_snippet_builder.dynamic_filter_template_woow_table` | QWeb dynamic filter template |
| `woow_snippet_builder.dynamic_filter_template_woow_timeline` | QWeb dynamic filter template |

**Data Records (noupdate=1):**

| XML ID | Model |
|--------|-------|
| `woow_snippet_builder.woow_filter_partners` | `ir.filters` |
| `woow_snippet_builder.woow_snippet_filter_partners` | `website.snippet.filter` |
| `woow_snippet_builder.woow_filter_companies` | `ir.filters` |
| `woow_snippet_builder.woow_snippet_filter_companies` | `website.snippet.filter` |

### 11.2 All data-* Attributes Per Snippet Type

**s_woow_dynamic_content:**

| Attribute | Purpose | Set by |
|-----------|---------|--------|
| `data-filter-mode` | `by_page_context` or `by_url_param` | Manual HTML edit |
| (inherited from DynamicSnippet) | `data-filter-id`, `data-template-key`, `data-number-of-elements`, etc. | CUSTOMIZE panel |

**s_woow_stat:**

| Attribute | JS key | Type | Default |
|-----------|--------|------|---------|
| `data-model-name` | `modelName` | string | `""` |
| `data-operation` | `operation` | enum | `"count"` |
| `data-stat-field` | `statField` | string | `""` |
| `data-group-by` | `groupBy` | string | `""` |
| `data-domain` | `domain` | string | `"[]"` |
| `data-sub-type` | `subType` | enum | `"default"` |
| `data-target-value` | `targetValue` | number | `"100"` |
| `data-threshold-warning` | `thresholdWarning` | number | `"50"` |
| `data-threshold-danger` | `thresholdDanger` | number | `"25"` |
| `data-previous-value` | `previousValue` | number | `"0"` |

**s_woow_chart:**

| Attribute | JS key | Type | Default |
|-----------|--------|------|---------|
| `data-model-name` | `modelName` | string | `""` |
| `data-chart-type` | `chartType` | enum | `"bar"` |
| `data-label-field` | `labelField` | string | `""` |
| `data-value-field` | `valueField` | string | `""` |
| `data-domain` | `domain` | string | `"[]"` |
| `data-gauge-max` | `gaugeMax` | number | `"100"` |
| `data-series-field` | `seriesField` | string | `""` |

**s_woow_data_table:**

| Attribute | JS key | Type | Default |
|-----------|--------|------|---------|
| `data-model-name` | `modelName` | string | `""` |
| `data-field-names` | `fieldNames` | string | `""` |
| `data-domain` | `domain` | string | `"[]"` |
| `data-page-size` | `pageSize` | number | `"25"` |
| `data-searchable` | `searchable` | enum | `"1"` |
| `data-sortable` | `sortable` | enum | `"1"` |

### 11.3 All RPC Endpoints

| Endpoint | Auth | Parameters | Returns |
|----------|------|-----------|---------|
| `/woow_snippet/available_models` | user | (none) | `[{model, name}]` |
| `/woow_snippet/model_fields` | user | `model_name` | `[{name, string, type}]` |
| `/woow_snippet/stat` | public | `model_name, operation, field_name, group_by, domain, sub_type, target_value, threshold_warning, threshold_danger, previous_value` | `{value, sub_type, breakdown[], ...}` |
| `/woow_snippet/chart` | public | `model_name, chart_type, label_field, value_field, domain, gauge_max, series_field` | `{labels[], datasets[], chart_type, gauge_max}` |
| `/woow_snippet/data_table` | public | `model_name, field_names, domain, offset, limit, sort_field, sort_order, search_term` | `{columns[], rows[], total, offset, limit}` |

### 11.4 Chart Type to Chart.js Type Mapping

| Module value | Chart.js `type` | Special config |
|-------------|----------------|----------------|
| `bar` | `bar` | -- |
| `line` | `line` | `fill:false, tension:0.3` |
| `pie` | `pie` | per-segment colors |
| `doughnut` | `doughnut` | per-segment colors |
| `radar` | `radar` | -- |
| `polarArea` | `polarArea` | per-segment colors |
| `bar_horizontal` | `bar` | `indexAxis:'y'` |
| `bar_stacked` | `bar` | `scales.x.stacked:true, scales.y.stacked:true` |
| `gauge` | `doughnut` | `circumference:180, rotation:-90, cutout:'75%'`, center label plugin |
| `funnel` | `bar` | `indexAxis:'y'`, data sorted descending, per-bar colors |

### 11.5 Operation to Implementation Mapping

| Operation | Odoo API call | Count key |
|-----------|-------------|-----------|
| `count` | `Model.search_count(domain)` | -- |
| `count_distinct` | `len(Model.read_group(domain, [field], [field]))` | -- |
| `sum` | `Model.read_group(domain, [field], [])[0][field]` | -- |
| `avg` | `read_group_result[field] / read_group_result['__count']` | `__count` |
| `min` | `Model.search(domain, order='{field} asc', limit=1)[field]` | -- |
| `max` | `Model.search(domain, order='{field} desc', limit=1)[field]` | -- |

### 11.6 CSS Selectors Used by Widgets

| Widget | Root selector | Content container | Interactive elements |
|--------|-------------|-------------------|---------------------|
| `s_woow_dynamic_content` | `.s_woow_dynamic_content` | (inherited from DynamicSnippet) | -- |
| `s_woow_stat` | `.s_woow_stat` | `.woow_stat_content` | -- |
| `s_woow_chart` | `.s_woow_chart` | `.woow_chart_content` | -- |
| `s_woow_data_table` | `.s_woow_data_table` | `.woow_data_table_content` | `.woow_dt_page`, `.woow_dt_sort`, `.woow_dt_search` |
