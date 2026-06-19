# Findings: HA Dashboard Research

## HA Models Available in Odoo (16 total)

### Core Models for Dashboard
| Model | Display Name | Key Fields |
|-------|-------------|------------|
| ha.instance | HA Instance | name, api_url, area_count, entity_count |
| ha.area | HA Area | name, area_id, ha_instance_id, entity_count |
| ha.device | HA Device | name, device_id, manufacturer, model, area_id, sw_version, hw_version |
| ha.entity | HA Entity | entity_id, name, domain, entity_state, device_id, area_id, last_changed |
| ha.entity.history | HA Entity History | entity_id, domain, entity_state, num_state, last_changed, last_updated |
| ha.entity.group | HA Entity Group | name, entity_ids, entity_count, description |
| ha.label | HA Label | name, label_id, area_count, device_count, entity_count |

### Field Types to Watch
- `area_id`: many2one → needs special handling for group_by (Odoo read_group works on m2o)
- `device_id`: many2one → same as above
- `ha_instance_id`: many2one → will be filtered
- `num_state`: float → can be aggregated (sum, avg, min, max)
- `domain`: char → good for group_by (sensor, switch, light, etc.)
- `manufacturer`: char → good for group_by
- `entity_state`: char → good for group_by
- `last_changed`: datetime → good for time-series label_field

## Current WoOW Snippet Builder Architecture

### API Endpoints
- `/woow_snippet/stat` — count/sum/avg/min/max with group_by
- `/woow_snippet/chart` — chart data (labels + datasets)
- `/woow_snippet/data_table` — paginated searchable table
- `/woow_snippet/available_models` — list whitelisted models
- `/woow_snippet/model_fields` — field introspection

### Whitelist Extension Method
In `controllers/main.py`:
```python
_DEFAULT_ALLOWED_MODELS = { 'res.partner', 'res.company', ... }

@classmethod
def _get_allowed_models(cls):
    return cls._DEFAULT_ALLOWED_MODELS
```
Simply add HA model names to `_DEFAULT_ALLOWED_MODELS` set.

### Snippet Data Attributes
- `data-model-name` — target model (e.g., "ha.device")
- `data-operation` — count/sum/avg/min/max
- `data-stat-field` — field to aggregate
- `data-group-by` — grouping field
- `data-chart-type` — bar/pie/line/doughnut/etc.
- `data-label-field` — x-axis field
- `data-value-field` — y-axis field
- `data-domain` — filter expression

## Container Setup
- Container: odoo-websitesnippet-web (port 9105)
- Bind mount: /var/tmp/vibe-kanban/worktrees/a19f-woow-snippet-bui/
- DB: odoo-websitesnippet / odoo-websitesnippet
- Files must be podman cp'd to container after editing
