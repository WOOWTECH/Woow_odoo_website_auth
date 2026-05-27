/** @odoo-module */
import publicWidget from "@web/legacy/js/public/public_widget";
import { rpc } from "@web/core/network/rpc";

/**
 * WoOW Stat Card — renders an aggregated KPI value with optional
 * progress bar, trend delta, or threshold indicator.  All configuration
 * is read from data-* attributes set by the CUSTOMIZE panel.
 */
publicWidget.registry.s_woow_stat = publicWidget.Widget.extend({
    selector: '.s_woow_stat',
    disabledInEditableMode: false,

    /**
     * @override
     */
    async start() {
        await this._super(...arguments);
        await this._loadAndRender();
    },

    // ------------------------------------------------------------------
    // Private
    // ------------------------------------------------------------------

    async _loadAndRender() {
        const ds = this.el.dataset;
        if (!ds.modelName) {
            this._renderPlaceholder();
            return;
        }

        try {
            const result = await rpc('/woow_snippet/stat', {
                model_name: ds.modelName,
                operation: ds.operation || 'count',
                field_name: ds.statField || '',
                group_by: ds.groupBy || '',
                domain: ds.domain || '[]',
                sub_type: ds.subType || 'default',
                target_value: parseFloat(ds.targetValue) || 100,
                threshold_warning: parseFloat(ds.thresholdWarning) || 50,
                threshold_danger: parseFloat(ds.thresholdDanger) || 25,
                previous_value: parseFloat(ds.previousValue) || 0,
            });
            this._renderStat(result);
        } catch (err) {
            this._renderError(err);
        }
    },

    _renderPlaceholder() {
        const el = this.el.querySelector('.woow_stat_content');
        if (el) {
            el.innerHTML = `
                <div class="text-center text-muted py-4">
                    <i class="fa fa-bar-chart fa-3x mb-2 d-block opacity-50"></i>
                    Configure this stat card in the Customize panel →
                </div>`;
        }
    },

    _renderError(err) {
        const el = this.el.querySelector('.woow_stat_content');
        if (el) {
            el.innerHTML = `
                <div class="text-center text-danger py-4">
                    <i class="fa fa-exclamation-triangle fa-2x mb-2 d-block"></i>
                    <small>${err.message || 'Error loading data'}</small>
                </div>`;
        }
    },

    _renderStat(result) {
        const el = this.el.querySelector('.woow_stat_content');
        if (!el) return;

        const value = this._formatNumber(result.value);
        const ds = this.el.dataset;
        const operation = ds.operation || 'count';
        const modelName = (ds.modelName || '').replace(/\./g, ' ');
        const label = `${operation.charAt(0).toUpperCase() + operation.slice(1)} of ${modelName}`;

        let html = '';
        switch (result.sub_type) {
            case 'progress':
                html = this._renderProgress(value, result, label);
                break;
            case 'trend':
                html = this._renderTrend(value, result, label);
                break;
            case 'threshold':
                html = this._renderThreshold(value, result, label);
                break;
            default:
                html = this._renderDefault(value, result, label);
        }

        // Append breakdown if present
        if (result.breakdown && result.breakdown.length) {
            html += this._renderBreakdown(result.breakdown);
        }

        el.innerHTML = html;
    },

    _renderDefault(value, result, label) {
        return `
            <div class="text-center py-3">
                <div class="display-4 fw-bold text-primary">${value}</div>
                <div class="text-muted mt-1">${label}</div>
            </div>`;
    },

    _renderProgress(value, result, label) {
        const pct = Math.min(result.percent || 0, 100);
        return `
            <div class="text-center py-3">
                <div class="display-4 fw-bold text-primary">${value}</div>
                <div class="text-muted mt-1">${label}</div>
                <div class="progress mt-3 mx-auto" style="max-width:300px; height:8px;">
                    <div class="progress-bar bg-primary" role="progressbar"
                         style="width:${pct}%"
                         aria-valuenow="${pct}" aria-valuemin="0"
                         aria-valuemax="100"></div>
                </div>
                <small class="text-muted">${pct}% of ${this._formatNumber(result.target)}</small>
            </div>`;
    },

    _renderTrend(value, result, label) {
        const delta = result.delta || 0;
        const deltaPct = result.delta_percent || 0;
        const isPositive = delta >= 0;
        const icon = isPositive ? 'fa-arrow-up' : 'fa-arrow-down';
        const color = isPositive ? 'text-success' : 'text-danger';
        return `
            <div class="text-center py-3">
                <div class="display-4 fw-bold text-primary">${value}</div>
                <div class="text-muted mt-1">${label}</div>
                <div class="mt-2 ${color}">
                    <i class="fa ${icon} me-1"></i>
                    <span class="fw-bold">${isPositive ? '+' : ''}${this._formatNumber(delta)}</span>
                    <span class="small">(${isPositive ? '+' : ''}${deltaPct}%)</span>
                </div>
            </div>`;
    },

    _renderThreshold(value, result, label) {
        const pct = Math.min(result.percent || 0, 100);
        const status = result.status || 'success';
        const colorMap = {success: 'bg-success', warning: 'bg-warning', danger: 'bg-danger'};
        const barClass = colorMap[status] || 'bg-primary';
        return `
            <div class="text-center py-3">
                <div class="display-4 fw-bold text-primary">${value}</div>
                <div class="text-muted mt-1">${label}</div>
                <div class="progress mt-3 mx-auto" style="max-width:300px; height:8px;">
                    <div class="progress-bar ${barClass}" role="progressbar"
                         style="width:${pct}%"
                         aria-valuenow="${pct}" aria-valuemin="0"
                         aria-valuemax="100"></div>
                </div>
                <small class="text-muted">${pct}% of target</small>
            </div>`;
    },

    _renderBreakdown(breakdown) {
        let rows = '';
        for (const item of breakdown) {
            rows += `
                <div class="d-flex justify-content-between py-1 border-bottom">
                    <span class="text-muted small">${item.label}</span>
                    <span class="fw-bold small">${this._formatNumber(item.value)}</span>
                </div>`;
        }
        return `<div class="mt-3 mx-auto" style="max-width:300px;">${rows}</div>`;
    },

    _formatNumber(num) {
        if (num === undefined || num === null) return '0';
        const n = typeof num === 'number' ? num : parseFloat(num);
        if (isNaN(n)) return String(num);
        if (Number.isInteger(n)) return n.toLocaleString();
        return n.toLocaleString(undefined, {
            minimumFractionDigits: 0,
            maximumFractionDigits: 2,
        });
    },
});

export default publicWidget.registry.s_woow_stat;
