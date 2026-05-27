/** @odoo-module */
import options from "@web_editor/js/editor/snippets.options";
import { rpc } from "@web/core/network/rpc";

/**
 * Editor options for the WoOW Data Table snippet.
 *
 * Dynamically populates the Model select and provides a text input for
 * comma-separated field names.
 */
options.registry.woow_data_table = options.Class.extend({

    async willStart() {
        const _super = this._super.bind(this);
        this.availableModels = await rpc('/woow_snippet/available_models');
        this.modelFields = [];
        return _super(...arguments);
    },

    _renderCustomXML(uiFragment) {
        const modelSelect = uiFragment.querySelector('[data-name="model_opt"]');
        if (modelSelect && this.availableModels) {
            for (const m of this.availableModels) {
                const btn = document.createElement('we-button');
                btn.dataset.selectDataAttribute = m.model;
                btn.textContent = m.name;
                modelSelect.appendChild(btn);
            }
        }
    },

    async selectDataAttribute(previewMode, widgetValue, params) {
        await this._super(...arguments);
        if (params.attributeName === 'modelName' && !previewMode) {
            if (widgetValue) {
                this.modelFields = await rpc('/woow_snippet/model_fields', {
                    model_name: widgetValue,
                });
                // Auto-populate fields_opt with first 5 field names as hint
                const hint = this.modelFields.slice(0, 5).map(f => f.name).join(',');
                this.$target[0].dataset.fieldNames = hint;
            } else {
                this.modelFields = [];
            }
            this.rerender = true;
            await this.updateUI();
            await this._refreshPublicWidgets();
        }
        if (['fieldNames', 'pageSize', 'searchable', 'sortable',
             'domain'].includes(params.attributeName)) {
            await this._refreshPublicWidgets();
        }
    },

    async updateUI() {
        if (this.rerender) {
            this.rerender = false;
            await this._rerenderXML();
            return;
        }
        await this._super(...arguments);
    },
});

export default options.registry.woow_data_table;
