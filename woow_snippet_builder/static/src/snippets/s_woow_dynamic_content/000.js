/** @odoo-module */
import DynamicSnippet from "@website/snippets/s_dynamic_snippet/000";
import publicWidget from "@web/legacy/js/public/public_widget";

/**
 * WoOW Dynamic Content — extends the native DynamicSnippet to support
 * contextual filtering via data-woow-ctx-* attributes and URL parameters.
 */
const WoowDynamicContent = DynamicSnippet.extend({
    selector: '.s_woow_dynamic_content',

    /**
     * Build an additional search domain based on contextual attributes set
     * on ancestor elements (data-woow-ctx-field="value") and URL query
     * parameters (e.g. ?partner_id=5 → [('partner_id','=',5)]).
     */
    _getSearchDomain() {
        const domain = this._super(...arguments);
        const ds = this.el.dataset;

        // Ancestor context attributes  (data-woow-ctx-<field>="value")
        if (ds.filterMode === 'by_page_context') {
            const ancestor = this.el.closest('[data-woow-ctx-model]');
            if (ancestor) {
                for (const [key, val] of Object.entries(ancestor.dataset)) {
                    if (key.startsWith('woowCtx') && key !== 'woowCtxModel') {
                        const field = key.replace('woowCtx', '')
                            .replace(/([A-Z])/g, '_$1').toLowerCase()
                            .replace(/^_/, '');
                        const parsed = parseInt(val, 10);
                        domain.push([field, '=', isNaN(parsed) ? val : parsed]);
                    }
                }
            }
        }

        // URL query parameters
        if (ds.filterMode === 'by_url_param') {
            const params = new URLSearchParams(window.location.search);
            for (const [key, val] of params.entries()) {
                if (key.startsWith('woow_')) {
                    const field = key.replace('woow_', '');
                    const parsed = parseInt(val, 10);
                    domain.push([field, '=', isNaN(parsed) ? val : parsed]);
                }
            }
        }

        return domain;
    },

    /**
     * Pass the woow_generic_mapping context so our custom
     * _filter_records_to_values override activates.
     */
    _getRpcParameters() {
        return Object.assign(this._super(...arguments), {
            with_context: {woow_generic_mapping: true},
        });
    },
});

publicWidget.registry.s_woow_dynamic_content = WoowDynamicContent;

export default WoowDynamicContent;
