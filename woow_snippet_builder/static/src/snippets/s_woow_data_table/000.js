/** @odoo-module */
import publicWidget from "@web/legacy/js/public/public_widget";
import { rpc } from "@web/core/network/rpc";

/**
 * WoOW Data Table — renders a paginated, searchable, sortable data table.
 * All configuration is read from data-* attributes.
 */
publicWidget.registry.s_woow_data_table = publicWidget.Widget.extend({
    selector: '.s_woow_data_table',
    disabledInEditableMode: false,
    events: {
        'click .woow_dt_page': '_onPageClick',
        'click .woow_dt_sort': '_onSortClick',
        'input .woow_dt_search': '_onSearchInput',
    },

    async start() {
        await this._super(...arguments);
        this._currentOffset = 0;
        this._sortField = '';
        this._sortOrder = 'asc';
        this._searchTerm = '';
        this._searchTimeout = null;
        await this._loadAndRender();
    },

    // ------------------------------------------------------------------
    // Event handlers
    // ------------------------------------------------------------------

    _onPageClick(ev) {
        ev.preventDefault();
        const offset = parseInt(ev.currentTarget.dataset.offset, 10);
        if (!isNaN(offset)) {
            this._currentOffset = offset;
            this._loadAndRender();
        }
    },

    _onSortClick(ev) {
        ev.preventDefault();
        const field = ev.currentTarget.dataset.field;
        if (this._sortField === field) {
            this._sortOrder = this._sortOrder === 'asc' ? 'desc' : 'asc';
        } else {
            this._sortField = field;
            this._sortOrder = 'asc';
        }
        this._currentOffset = 0;
        this._loadAndRender();
    },

    _onSearchInput(ev) {
        clearTimeout(this._searchTimeout);
        this._searchTimeout = setTimeout(() => {
            this._searchTerm = ev.target.value;
            this._currentOffset = 0;
            this._loadAndRender();
        }, 300);
    },

    // ------------------------------------------------------------------
    // Private
    // ------------------------------------------------------------------

    async _loadAndRender() {
        const ds = this.el.dataset;
        if (!ds.modelName || !ds.fieldNames) {
            this._renderPlaceholder();
            return;
        }

        try {
            const result = await rpc('/woow_snippet/data_table', {
                model_name: ds.modelName,
                field_names: ds.fieldNames,
                domain: ds.domain || '[]',
                offset: this._currentOffset,
                limit: parseInt(ds.pageSize, 10) || 25,
                sort_field: this._sortField,
                sort_order: this._sortOrder,
                search_term: this._searchTerm,
            });
            this._renderTable(result, ds);
        } catch (err) {
            this._renderError(err);
        }
    },

    _renderPlaceholder() {
        const el = this.el.querySelector('.woow_data_table_content');
        if (el) {
            el.innerHTML = `
                <div class="text-center text-muted py-4">
                    <i class="fa fa-table fa-3x mb-2 d-block opacity-50"></i>
                    Configure this data table in the Customize panel →
                </div>`;
        }
    },

    _renderError(err) {
        const el = this.el.querySelector('.woow_data_table_content');
        if (el) {
            el.innerHTML = `
                <div class="text-center text-danger py-4">
                    <i class="fa fa-exclamation-triangle fa-2x mb-2 d-block"></i>
                    <small>${err.message || 'Error loading table data'}</small>
                </div>`;
        }
    },

    _renderTable(result, ds) {
        const el = this.el.querySelector('.woow_data_table_content');
        if (!el) return;

        const searchable = ds.searchable !== '0';
        const sortable = ds.sortable !== '0';
        const columns = result.columns || [];
        const rows = result.rows || [];
        const total = result.total || 0;
        const offset = result.offset || 0;
        const limit = result.limit || 25;

        let html = '';

        // Search bar
        if (searchable) {
            html += `
                <div class="mb-3">
                    <input type="text" class="form-control woow_dt_search"
                           placeholder="Search..." value="${this._escapeHtml(this._searchTerm)}"/>
                </div>`;
        }

        // Table
        html += '<div class="table-responsive"><table class="table table-sm table-hover">';

        // Header
        html += '<thead class="table-light"><tr>';
        for (const col of columns) {
            if (sortable) {
                let icon = 'fa-sort';
                if (this._sortField === col.name) {
                    icon = this._sortOrder === 'asc' ? 'fa-sort-asc' : 'fa-sort-desc';
                }
                html += `<th class="woow_dt_sort" data-field="${col.name}"
                             role="button" style="cursor:pointer;">
                    ${this._escapeHtml(col.string)}
                    <i class="fa ${icon} ms-1 small opacity-50"></i>
                </th>`;
            } else {
                html += `<th>${this._escapeHtml(col.string)}</th>`;
            }
        }
        html += '</tr></thead>';

        // Body
        html += '<tbody>';
        if (rows.length === 0) {
            html += `<tr><td colspan="${columns.length}" class="text-center text-muted py-3">
                No records found</td></tr>`;
        }
        for (const row of rows) {
            html += '<tr>';
            for (const col of columns) {
                const val = row[col.name];
                const display = val === null || val === undefined || val === false
                    ? ''
                    : String(val);
                html += `<td>${this._escapeHtml(display)}</td>`;
            }
            html += '</tr>';
        }
        html += '</tbody></table></div>';

        // Pagination
        if (total > limit) {
            const totalPages = Math.ceil(total / limit);
            const currentPage = Math.floor(offset / limit);
            html += '<nav><ul class="pagination pagination-sm justify-content-center">';
            for (let i = 0; i < totalPages && i < 10; i++) {
                const pgOffset = i * limit;
                const active = i === currentPage ? 'active' : '';
                html += `<li class="page-item ${active}">
                    <a href="#" class="page-link woow_dt_page"
                       data-offset="${pgOffset}">${i + 1}</a>
                </li>`;
            }
            if (totalPages > 10) {
                html += `<li class="page-item disabled">
                    <span class="page-link">... (${totalPages} pages)</span>
                </li>`;
            }
            html += '</ul></nav>';
        }

        // Record count
        html += `<div class="text-muted small text-center">
            ${Math.min(offset + 1, total)}–${Math.min(offset + limit, total)} of ${total}
        </div>`;

        el.innerHTML = html;
    },

    _escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    },
});

export default publicWidget.registry.s_woow_data_table;
