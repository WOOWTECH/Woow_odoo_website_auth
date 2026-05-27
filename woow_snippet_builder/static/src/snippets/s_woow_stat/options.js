/** @odoo-module */
import options from "@web_editor/js/editor/snippets.options";
import { rpc } from "@web/core/network/rpc";

/**
 * Editor options for the WoOW Stat Card snippet.
 *
 * Dynamically populates Model / Field / Group By selects from the
 * /woow_snippet/available_models and /woow_snippet/model_fields endpoints.
 */
options.registry.woow_stat = options.Class.extend({

    /**
     * Fetch available models before the option panel renders.
     */
    async willStart() {
        const _super = this._super.bind(this);
        this.availableModels = await rpc('/woow_snippet/available_models');
        this.modelFields = [];
        return _super(...arguments);
    },

    /**
     * When the Model select changes, fetch the fields and refresh the
     * Field / Group By dropdowns.
     */
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
        if (['operation', 'statField', 'groupBy', 'subType', 'targetValue',
             'previousValue', 'domain'].includes(params.attributeName)) {
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

    /**
     * Populate the Model, Field, and Group By selects with dynamic entries.
     */
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

        // Populate field_opt and group_by_opt with numeric-capable fields
        const fieldSelect = uiFragment.querySelector('[data-name="field_opt"]');
        const groupBySelect = uiFragment.querySelector('[data-name="group_by_opt"]');

        if (this.modelFields && this.modelFields.length) {
            for (const f of this.modelFields) {
                // Field select — only numeric fields for aggregation
                if (fieldSelect && ['integer', 'float', 'monetary'].includes(f.type)) {
                    const btn = document.createElement('we-button');
                    btn.dataset.selectDataAttribute = f.name;
                    btn.textContent = f.string;
                    fieldSelect.appendChild(btn);
                }

                // Group by — allow selection/many2one/char/date fields
                if (groupBySelect &&
                    ['selection', 'many2one', 'char', 'date', 'datetime',
                     'boolean'].includes(f.type)) {
                    const btn = document.createElement('we-button');
                    btn.dataset.selectDataAttribute = f.name;
                    btn.textContent = f.string;
                    groupBySelect.appendChild(btn);
                }
            }
        }
    },
});

export default options.registry.woow_stat;
