from odoo import models


class WebsiteSnippetFilter(models.Model):
    _inherit = 'website.snippet.filter'

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
