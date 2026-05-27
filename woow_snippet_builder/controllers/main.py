import json
import logging

from odoo import http
from odoo.http import request
from odoo.tools.safe_eval import safe_eval

_logger = logging.getLogger(__name__)

# Models that public endpoints are allowed to query.  Extend this set via
# the ``_woow_allowed_models`` method on your custom controller if you need
# to support additional models without modifying this file.
_DEFAULT_ALLOWED_MODELS = {
    'res.partner',
    'res.company',
    'res.users',
    'product.template',
    'product.product',
    'sale.order',
    'sale.order.line',
    'purchase.order',
    'purchase.order.line',
    'account.move',
    'account.move.line',
    'stock.picking',
    'stock.move',
    'project.project',
    'project.task',
    'hr.employee',
    'hr.department',
    'crm.lead',
    'helpdesk.ticket',
    'event.event',
    'event.registration',
    'survey.survey',
    'survey.user_input',
    'fleet.vehicle',
    'maintenance.request',
    'lunch.order',
    'website.page',
    'blog.post',
}

_VALID_SORT_ORDERS = {'asc', 'desc'}
_VALID_OPERATIONS = {'count', 'sum', 'avg', 'min', 'max', 'count_distinct'}


def _safe_domain(domain_str):
    """Parse a domain string safely, returning an empty domain on failure."""
    if not domain_str or domain_str == '[]':
        return []
    try:
        return safe_eval(domain_str, {'True': True, 'False': False, 'None': None})
    except Exception:
        _logger.warning('Invalid domain string: %s', domain_str)
        return []


class WoowSnippetController(http.Controller):

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_allowed_models(self):
        """Return the set of model technical names that may be queried by
        the public snippet endpoints.  Override to extend."""
        return _DEFAULT_ALLOWED_MODELS

    def _validate_model(self, model_name):
        """Raise if the model is not in the whitelist or doesn't exist."""
        if model_name not in self._get_allowed_models():
            raise ValueError(f'Model {model_name!r} is not allowed')
        if model_name not in request.env:
            raise ValueError(f'Model {model_name!r} does not exist')

    # ------------------------------------------------------------------
    # Editor-only RPC (auth='user')
    # ------------------------------------------------------------------

    @http.route('/woow_snippet/available_models', type='json', auth='user',
                website=True)
    def get_available_models(self):
        """Return a list of models available for snippet configuration.

        Each entry is ``{'model': 'res.partner', 'name': 'Contact'}``.
        """
        result = []
        for model_name in sorted(self._get_allowed_models()):
            model = request.env.get(model_name)
            if model is not None:
                try:
                    description = model._description or model_name
                except Exception:
                    description = model_name
                result.append({
                    'model': model_name,
                    'name': description,
                })
        return result

    @http.route('/woow_snippet/model_fields', type='json', auth='user',
                website=True)
    def get_model_fields(self, model_name):
        """Return the list of readable fields for *model_name*.

        Each entry is ``{'name': 'field_name', 'string': 'Field Label',
        'type': 'char'}``.
        """
        self._validate_model(model_name)
        Model = request.env[model_name]
        result = []
        for fname, field in sorted(Model._fields.items()):
            if fname.startswith('_') or not field.store:
                continue
            # Skip relational / binary blobs that are not useful for
            # stat / chart / table display.
            if field.type in ('one2many', 'binary', 'serialized', 'properties',
                              'properties_definition'):
                continue
            result.append({
                'name': fname,
                'string': field.string or fname,
                'type': field.type,
            })
        return result

    # ------------------------------------------------------------------
    # Public data endpoints (auth='public')
    # ------------------------------------------------------------------

    @http.route('/woow_snippet/stat', type='json', auth='public',
                website=True, readonly=True)
    def get_stat(self, model_name, operation='count', field_name='',
                 group_by='', domain='[]', sub_type='default',
                 target_value=100, threshold_warning=50,
                 threshold_danger=25, previous_value=0):
        """Return aggregated stat data for the Stat Card snippet."""
        self._validate_model(model_name)
        if operation not in _VALID_OPERATIONS:
            raise ValueError(f'Invalid operation: {operation!r}')

        Model = request.env[model_name].sudo()
        parsed_domain = _safe_domain(domain)

        if operation == 'count':
            value = Model.search_count(parsed_domain)
        elif operation == 'count_distinct' and field_name:
            results = Model.read_group(parsed_domain, [field_name],
                                       [field_name])
            value = len(results)
        elif field_name:
            results = Model.read_group(parsed_domain, [field_name], [])
            if results:
                agg_key = f'{field_name}'
                raw = results[0].get(agg_key, 0) or 0
                if operation == 'sum':
                    value = raw
                elif operation == 'avg':
                    count = results[0].get('__count', 1) or 1
                    value = raw / count if count else 0
                elif operation == 'min':
                    recs = Model.search(parsed_domain, order=f'{field_name} asc',
                                        limit=1)
                    value = recs[field_name] if recs else 0
                elif operation == 'max':
                    recs = Model.search(parsed_domain, order=f'{field_name} desc',
                                        limit=1)
                    value = recs[field_name] if recs else 0
                else:
                    value = raw
            else:
                value = 0
        else:
            value = Model.search_count(parsed_domain)

        # Group-by breakdown
        breakdown = []
        if group_by:
            try:
                groups = Model.read_group(parsed_domain,
                                          [field_name] if field_name else [],
                                          [group_by])
                for g in groups:
                    label = g.get(group_by)
                    if isinstance(label, (list, tuple)):
                        label = label[1] if len(label) > 1 else label[0]
                    count = g.get(f'{group_by}_count', g.get('__count', 0))
                    breakdown.append({'label': str(label), 'value': count})
            except Exception:
                pass

        target_value = float(target_value) if target_value else 100
        previous_value = float(previous_value) if previous_value else 0

        result = {
            'value': value,
            'sub_type': sub_type,
            'breakdown': breakdown,
        }
        if sub_type == 'progress':
            result['target'] = target_value
            result['percent'] = round(value / target_value * 100, 1) if target_value else 0
        elif sub_type == 'trend':
            delta = value - previous_value
            result['delta'] = delta
            result['delta_percent'] = (
                round(delta / previous_value * 100, 1) if previous_value else 0
            )
        elif sub_type == 'threshold':
            result['target'] = target_value
            threshold_warning = float(threshold_warning) if threshold_warning else 50
            threshold_danger = float(threshold_danger) if threshold_danger else 25
            pct = round(value / target_value * 100, 1) if target_value else 0
            result['percent'] = pct
            if pct >= threshold_warning:
                result['status'] = 'success'
            elif pct >= threshold_danger:
                result['status'] = 'warning'
            else:
                result['status'] = 'danger'

        return result

    @http.route('/woow_snippet/chart', type='json', auth='public',
                website=True, readonly=True)
    def get_chart(self, model_name, chart_type='bar', label_field='',
                  value_field='', domain='[]', gauge_max=100,
                  series_field=''):
        """Return aggregated chart data for the Chart snippet."""
        self._validate_model(model_name)
        Model = request.env[model_name].sudo()
        parsed_domain = _safe_domain(domain)

        if not label_field or not value_field:
            return {'labels': [], 'datasets': []}

        if series_field:
            # Multi-series: group by both label and series fields
            try:
                groups = Model.read_group(
                    parsed_domain, [value_field],
                    [label_field, series_field], lazy=False,
                )
            except Exception:
                groups = []

            label_set = []
            series_map = {}
            for g in groups:
                lbl = g.get(label_field)
                if isinstance(lbl, (list, tuple)):
                    lbl = lbl[1] if len(lbl) > 1 else lbl[0]
                lbl = str(lbl) if lbl else ''

                ser = g.get(series_field)
                if isinstance(ser, (list, tuple)):
                    ser = ser[1] if len(ser) > 1 else ser[0]
                ser = str(ser) if ser else ''

                val = g.get(value_field, 0) or 0

                if lbl not in label_set:
                    label_set.append(lbl)
                series_map.setdefault(ser, {})[lbl] = val

            datasets = []
            for series_name, data_map in series_map.items():
                datasets.append({
                    'label': series_name,
                    'data': [data_map.get(l, 0) for l in label_set],
                })

            return {
                'labels': label_set,
                'datasets': datasets,
                'chart_type': chart_type,
                'gauge_max': float(gauge_max) if gauge_max else 100,
            }
        else:
            # Single series
            try:
                groups = Model.read_group(parsed_domain, [value_field],
                                          [label_field])
            except Exception:
                groups = []

            labels = []
            data = []
            for g in groups:
                lbl = g.get(label_field)
                if isinstance(lbl, (list, tuple)):
                    lbl = lbl[1] if len(lbl) > 1 else lbl[0]
                labels.append(str(lbl) if lbl else '')
                data.append(g.get(value_field, 0) or 0)

            return {
                'labels': labels,
                'datasets': [{'label': value_field, 'data': data}],
                'chart_type': chart_type,
                'gauge_max': float(gauge_max) if gauge_max else 100,
            }

    @http.route('/woow_snippet/data_table', type='json', auth='public',
                website=True, readonly=True)
    def get_data_table(self, model_name, field_names='', domain='[]',
                       offset=0, limit=25, sort_field='', sort_order='asc',
                       search_term=''):
        """Return paginated table data for the Data Table snippet."""
        self._validate_model(model_name)
        Model = request.env[model_name].sudo()
        parsed_domain = _safe_domain(domain)

        # Parse requested fields
        fields = [f.strip() for f in field_names.split(',') if f.strip()]
        if not fields:
            return {'columns': [], 'rows': [], 'total': 0}

        # Build column metadata
        columns = []
        valid_fields = []
        for fname in fields:
            field = Model._fields.get(fname)
            if field:
                columns.append({
                    'name': fname,
                    'string': field.string or fname,
                    'type': field.type,
                })
                valid_fields.append(fname)

        if not valid_fields:
            return {'columns': [], 'rows': [], 'total': 0}

        # Free-text search across char/text fields
        if search_term:
            search_domains = []
            for fname in valid_fields:
                field = Model._fields.get(fname)
                if field and field.type in ('char', 'text', 'html'):
                    search_domains.append([(fname, 'ilike', search_term)])
            if search_domains:
                from odoo.osv.expression import OR
                parsed_domain = parsed_domain + OR(search_domains)

        # Sorting
        order = None
        if sort_field and sort_field in valid_fields:
            so = sort_order if sort_order in _VALID_SORT_ORDERS else 'asc'
            order = f'{sort_field} {so}'

        # Clamp offset / limit
        offset = max(0, int(offset))
        limit = min(max(1, int(limit)), 100)

        total = Model.search_count(parsed_domain)
        records = Model.search(parsed_domain, offset=offset, limit=limit,
                               order=order)

        rows = []
        for rec in records:
            row = {'id': rec.id}
            for fname in valid_fields:
                val = rec[fname]
                if hasattr(val, 'display_name'):
                    val = val.display_name
                elif hasattr(val, 'ids'):
                    val = ', '.join(val.mapped('display_name'))
                row[fname] = val
            rows.append(row)

        return {
            'columns': columns,
            'rows': rows,
            'total': total,
            'offset': offset,
            'limit': limit,
        }
