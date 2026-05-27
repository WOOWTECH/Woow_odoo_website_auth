/** @odoo-module */
import publicWidget from "@web/legacy/js/public/public_widget";
import { rpc } from "@web/core/network/rpc";
import { loadJS } from "@web/core/assets";

// Palette used for chart datasets
const COLORS = [
    '#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6',
    '#EC4899', '#06B6D4', '#84CC16', '#F97316', '#6366F1',
    '#14B8A6', '#E11D48', '#0EA5E9', '#A855F7', '#22C55E',
];

/**
 * WoOW Chart — renders a Chart.js visualisation from aggregated data.
 * All configuration is read from data-* attributes.
 */
publicWidget.registry.s_woow_chart = publicWidget.Widget.extend({
    selector: '.s_woow_chart',
    disabledInEditableMode: false,

    async start() {
        await this._super(...arguments);
        await this._loadAndRender();
    },

    destroy() {
        this._destroyChart();
        this._super(...arguments);
    },

    // ------------------------------------------------------------------
    // Private
    // ------------------------------------------------------------------

    async _loadAndRender() {
        const ds = this.el.dataset;
        if (!ds.modelName || !ds.labelField || !ds.valueField) {
            this._renderPlaceholder();
            return;
        }

        try {
            const result = await rpc('/woow_snippet/chart', {
                model_name: ds.modelName,
                chart_type: ds.chartType || 'bar',
                label_field: ds.labelField,
                value_field: ds.valueField,
                domain: ds.domain || '[]',
                gauge_max: parseFloat(ds.gaugeMax) || 100,
                series_field: ds.seriesField || '',
            });
            await this._renderChart(result);
        } catch (err) {
            this._renderError(err);
        }
    },

    _renderPlaceholder() {
        const el = this.el.querySelector('.woow_chart_content');
        if (el) {
            el.innerHTML = `
                <div class="text-center text-muted py-5">
                    <i class="fa fa-pie-chart fa-3x mb-2 d-block opacity-50"></i>
                    Configure this chart in the Customize panel →
                </div>`;
        }
    },

    _renderError(err) {
        const el = this.el.querySelector('.woow_chart_content');
        if (el) {
            el.innerHTML = `
                <div class="text-center text-danger py-4">
                    <i class="fa fa-exclamation-triangle fa-2x mb-2 d-block"></i>
                    <small>${err.message || 'Error loading chart data'}</small>
                </div>`;
        }
    },

    _destroyChart() {
        if (this._chartInstance) {
            this._chartInstance.destroy();
            this._chartInstance = null;
        }
    },

    async _renderChart(result) {
        const container = this.el.querySelector('.woow_chart_content');
        if (!container) return;

        // Ensure Chart.js is loaded
        if (typeof Chart === 'undefined') {
            await loadJS('/web/static/lib/Chart/Chart.js');
        }
        if (typeof Chart === 'undefined') {
            this._renderError({message: 'Chart.js library not available'});
            return;
        }

        this._destroyChart();
        container.innerHTML = '<canvas></canvas>';
        const canvas = container.querySelector('canvas');
        const ctx = canvas.getContext('2d');
        const chartType = result.chart_type || 'bar';

        let config;
        if (chartType === 'gauge') {
            config = this._buildGaugeConfig(result);
        } else if (chartType === 'funnel') {
            config = this._buildFunnelConfig(result);
        } else {
            config = this._buildStandardConfig(result, chartType);
        }

        this._chartInstance = new Chart(ctx, config);
    },

    _buildStandardConfig(result, chartType) {
        const isPie = ['pie', 'doughnut', 'polarArea'].includes(chartType);
        const isHorizontal = chartType === 'bar_horizontal';
        const isStacked = chartType === 'bar_stacked';

        // Map internal type names to Chart.js types
        let type = chartType;
        if (isHorizontal || isStacked) type = 'bar';

        const datasets = result.datasets.map((ds, idx) => {
            const color = COLORS[idx % COLORS.length];
            const entry = {
                label: ds.label,
                data: ds.data,
            };
            if (isPie) {
                entry.backgroundColor = ds.data.map((_, i) => COLORS[i % COLORS.length]);
            } else {
                entry.backgroundColor = color + '99';
                entry.borderColor = color;
                entry.borderWidth = 2;
            }
            if (type === 'line') {
                entry.fill = false;
                entry.tension = 0.3;
            }
            return entry;
        });

        const config = {
            type,
            data: {
                labels: result.labels,
                datasets,
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: datasets.length > 1 || isPie,
                    },
                },
            },
        };

        if (isHorizontal) {
            config.options.indexAxis = 'y';
        }
        if (isStacked) {
            config.options.scales = {
                x: {stacked: true},
                y: {stacked: true},
            };
        }

        return config;
    },

    _buildGaugeConfig(result) {
        const value = result.datasets[0]?.data[0] || 0;
        const max = result.gauge_max || 100;
        const pct = Math.min(value / max * 100, 100);
        return {
            type: 'doughnut',
            data: {
                datasets: [{
                    data: [pct, 100 - pct],
                    backgroundColor: [COLORS[0], '#e5e7eb'],
                    borderWidth: 0,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                circumference: 180,
                rotation: -90,
                cutout: '75%',
                plugins: {
                    legend: {display: false},
                    tooltip: {enabled: false},
                },
            },
            plugins: [{
                id: 'gaugeLabel',
                afterDraw(chart) {
                    const {ctx: c, chartArea: {left, right, top, bottom}} = chart;
                    const cx = (left + right) / 2;
                    const cy = bottom - 10;
                    c.save();
                    c.textAlign = 'center';
                    c.font = 'bold 28px sans-serif';
                    c.fillStyle = COLORS[0];
                    c.fillText(value.toLocaleString(), cx, cy);
                    c.font = '14px sans-serif';
                    c.fillStyle = '#6b7280';
                    c.fillText(`/ ${max.toLocaleString()}`, cx, cy + 20);
                    c.restore();
                },
            }],
        };
    },

    _buildFunnelConfig(result) {
        // Funnel rendered as horizontal bar chart sorted descending
        const data = result.datasets[0]?.data || [];
        const labels = result.labels || [];

        // Sort descending by value
        const pairs = labels.map((l, i) => ({label: l, value: data[i] || 0}));
        pairs.sort((a, b) => b.value - a.value);

        return {
            type: 'bar',
            data: {
                labels: pairs.map(p => p.label),
                datasets: [{
                    data: pairs.map(p => p.value),
                    backgroundColor: pairs.map((_, i) => COLORS[i % COLORS.length] + '99'),
                    borderColor: pairs.map((_, i) => COLORS[i % COLORS.length]),
                    borderWidth: 1,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                indexAxis: 'y',
                plugins: {legend: {display: false}},
                scales: {
                    x: {beginAtZero: true},
                },
            },
        };
    },
});

export default publicWidget.registry.s_woow_chart;
