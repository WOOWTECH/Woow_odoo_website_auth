/** @odoo-module */
import options from "@web_editor/js/editor/snippets.options";
import { rpc } from "@web/core/network/rpc";

/**
 * Editor options for the WoOW Chart snippet.
 *
 * Dynamically populates Model / Label Field / Value Field / Series Field
 * selects from backend RPC endpoints.
 */
options.registry.woow_chart = options.Class.extend({

    async willStart() {
        const _super = this._super.bind(this);
        this.availableModels = await rpc('/woow_snippet/available_models');
        this.modelFields = [];
        return _super(...arguments);
    },

    _renderCustomXML(uiFragment) {
        // Populate model_opt
        const modelSelect = uiFragment.querySelector('[data-name="model_opt"]');
        if (modelSelect && this.availableModels) {
            for (const m of this.availableModels) {
                const btn = document.createElement('we-button');
                btn.dataset.selectDataAttribute = m.model;
                btn.textContent = m.name;
                modelSelect.appendChild(btn);
            }
        }

        // Populate label / value / series field selects
        const labelSelect = uiFragment.querySelector('[data-name="label_field_opt"]');
        const valueSelect = uiFragment.querySelector('[data-name="value_field_opt"]');
        const seriesSelect = uiFragment.querySelector('[data-name="series_field_opt"]');

        if (this.modelFields && this.modelFields.length) {
            for (const f of this.modelFields) {
                // Label field — categorical types
                if (labelSelect &&
                    ['char', 'selection', 'many2one', 'date', 'datetime',
                     'boolean'].includes(f.type)) {
                    const btn = document.createElement('we-button');
                    btn.dataset.selectDataAttribute = f.name;
                    btn.textContent = f.string;
                    labelSelect.appendChild(btn);
                }

                // Value field — numeric types
                if (valueSelect &&
                    ['integer', 'float', 'monetary'].includes(f.type)) {
                    const btn = document.createElement('we-button');
                    btn.dataset.selectDataAttribute = f.name;
                    btn.textContent = f.string;
                    valueSelect.appendChild(btn);
                }

                // Series field — categorical types
                if (seriesSelect &&
                    ['char', 'selection', 'many2one', 'boolean'].includes(f.type)) {
                    const btn = document.createElement('we-button');
                    btn.dataset.selectDataAttribute = f.name;
                    btn.textContent = f.string;
                    seriesSelect.appendChild(btn);
                }
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
            } else {
                this.modelFields = [];
            }
            this.rerender = true;
            await this.updateUI();
            await this._refreshPublicWidgets();
        }
        if (['chartType', 'labelField', 'valueField', 'seriesField',
             'gaugeMax', 'domain'].includes(params.attributeName)) {
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

export default options.registry.woow_chart;
