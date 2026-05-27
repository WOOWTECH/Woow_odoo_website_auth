import logging
from ast import literal_eval

from lxml import etree, html as lxml_html

from odoo import models
from odoo.osv import expression

_logger = logging.getLogger(__name__)


class WebsiteSnippetFilter(models.Model):
    _inherit = 'website.snippet.filter'

    # ------------------------------------------------------------------
    # Render override
    # ------------------------------------------------------------------

    def _render(self, template_key, limit, search_domain=None,
                with_sample=False, **custom_template_data):
        """Override to handle WoOW generic templates.

        The native implementation rejects template keys that don't embed
        the model technical name (e.g. ``res_partner``).  WoOW templates
        use model-agnostic names like ``dynamic_filter_template_woow_card``
        so they can render records from *any* model.

        When we detect a WoOW template key we skip the model-name guard
        and make sure the ``woow_generic_mapping`` context flag is active
        so that ``_filter_records_to_values`` maps fields generically.
        """
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

    # ------------------------------------------------------------------
    # WoOW-specific record loading (keeps sudo)
    # ------------------------------------------------------------------

    def _woow_prepare_values(self, limit=None, search_domain=None):
        """Like ``_prepare_values`` but keeps sudo so that models without
        public access rules (e.g. ``res.partner``) can still be rendered
        on the website.  Access is controlled by the allowed-models
        whitelist in the controller instead.
        """
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

    # ------------------------------------------------------------------
    # Generic field mapping
    # ------------------------------------------------------------------

    def _filter_records_to_values(self, records, is_sample=False):
        """Override to map arbitrary fields to generic keys when woow_generic_mapping
        context flag is set.

        This allows QWeb templates to use stable keys (field_0, field_1, …, image)
        regardless of the actual model field names, enabling a single set of
        templates to render records from any model.
        """
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
