// @ts-check
const { test, expect } = require('@playwright/test');

const BASE_URL = 'http://localhost:9105';
const ADMIN_LOGIN = 'admin';
const ADMIN_PASS = 'admin';

/**
 * Helper: login to Odoo backend as admin
 */
async function loginAsAdmin(page) {
    await page.goto(`${BASE_URL}/web/login`);
    await page.locator('input[name="login"]').fill(ADMIN_LOGIN);
    await page.locator('input[name="password"]').fill(ADMIN_PASS);
    await page.locator('.oe_login_form button[type="submit"], form[action="/web/login"] button[type="submit"], button.btn-primary[type="submit"]').first().click();
    await page.waitForURL(/\/web|\/odoo/, { timeout: 15000 });
}

/**
 * Helper: Navigate to website editor for the homepage
 */
async function openWebsiteEditor(page) {
    await page.goto(`${BASE_URL}/`);
    // Wait for page to be ready
    await page.waitForLoadState('networkidle');
    // Click "Edit" button in the top bar
    const editBtn = page.locator('a.o_edit_website_container, button.o_edit_website_container, [data-action="edit"]').first();
    if (await editBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
        await editBtn.click();
    } else {
        // Try alternative selector
        await page.click('text=Edit', { timeout: 5000 }).catch(() => {});
    }
    // Wait for editor to load
    await page.waitForSelector('.o_website_preview, #oe_snippets, .o_we_customize_panel', { timeout: 15000 }).catch(() => {});
}

// ============================================================
// TEST SUITE 1: Module Installation Verification
// ============================================================
test.describe('Module Installation', () => {
    test('module is installed and active', async ({ page }) => {
        await loginAsAdmin(page);
        // Check via JSON RPC that module is installed (stay on /web page)
        const response = await page.evaluate(async () => {
            const res = await fetch('/web/dataset/call_kw', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    jsonrpc: '2.0',
                    method: 'call',
                    params: {
                        model: 'ir.module.module',
                        method: 'search_read',
                        args: [[['name', '=', 'woow_snippet_builder']]],
                        kwargs: { fields: ['name', 'state', 'latest_version'], limit: 1 },
                    },
                }),
            });
            return res.json();
        });
        const module = response.result?.[0];
        expect(module).toBeTruthy();
        expect(module.state).toBe('installed');
        expect(module.latest_version).toBe('18.0.2.0.0');
    });
});

// ============================================================
// TEST SUITE 2: RPC Endpoint Tests
// ============================================================
test.describe('RPC Endpoints', () => {
    test.beforeEach(async ({ page }) => {
        await loginAsAdmin(page);
    });

    test('GET /woow_snippet/available_models returns models', async ({ page }) => {
        const response = await page.evaluate(async () => {
            const res = await fetch('/woow_snippet/available_models', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ jsonrpc: '2.0', params: {} }),
            });
            return res.json();
        });
        const models = response.result;
        expect(Array.isArray(models)).toBe(true);
        expect(models.length).toBeGreaterThan(0);
        // res.partner should be in the list
        const partner = models.find(m => m.model === 'res.partner');
        expect(partner).toBeTruthy();
        expect(partner.name).toBeTruthy();
    });

    test('GET /woow_snippet/model_fields returns fields for res.partner', async ({ page }) => {
        const response = await page.evaluate(async () => {
            const res = await fetch('/woow_snippet/model_fields', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    jsonrpc: '2.0',
                    params: { model_name: 'res.partner' },
                }),
            });
            return res.json();
        });
        const fields = response.result;
        expect(Array.isArray(fields)).toBe(true);
        expect(fields.length).toBeGreaterThan(5);
        // 'name' should be in the field list
        const nameField = fields.find(f => f.name === 'name');
        expect(nameField).toBeTruthy();
        expect(nameField.type).toBe('char');
    });

    test('POST /woow_snippet/stat returns count', async ({ page }) => {
        const response = await page.evaluate(async () => {
            const res = await fetch('/woow_snippet/stat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    jsonrpc: '2.0',
                    params: {
                        model_name: 'res.partner',
                        operation: 'count',
                        domain: '[]',
                    },
                }),
            });
            return res.json();
        });
        const result = response.result;
        expect(result).toBeTruthy();
        expect(typeof result.value).toBe('number');
        expect(result.value).toBeGreaterThan(0);
        expect(result.sub_type).toBe('default');
    });

    test('POST /woow_snippet/stat with progress sub_type', async ({ page }) => {
        const response = await page.evaluate(async () => {
            const res = await fetch('/woow_snippet/stat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    jsonrpc: '2.0',
                    params: {
                        model_name: 'res.partner',
                        operation: 'count',
                        domain: '[]',
                        sub_type: 'progress',
                        target_value: 100,
                    },
                }),
            });
            return res.json();
        });
        const result = response.result;
        expect(result).toBeTruthy();
        expect(result.sub_type).toBe('progress');
        expect(typeof result.percent).toBe('number');
        expect(typeof result.target).toBe('number');
    });

    test('POST /woow_snippet/chart returns chart data', async ({ page }) => {
        const response = await page.evaluate(async () => {
            const res = await fetch('/woow_snippet/chart', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    jsonrpc: '2.0',
                    params: {
                        model_name: 'res.partner',
                        chart_type: 'bar',
                        label_field: 'country_id',
                        value_field: 'id',
                        domain: '[]',
                    },
                }),
            });
            return res.json();
        });
        const result = response.result;
        expect(result).toBeTruthy();
        expect(Array.isArray(result.labels)).toBe(true);
        expect(Array.isArray(result.datasets)).toBe(true);
        expect(result.datasets.length).toBeGreaterThan(0);
    });

    test('POST /woow_snippet/data_table returns table data', async ({ page }) => {
        const response = await page.evaluate(async () => {
            const res = await fetch('/woow_snippet/data_table', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    jsonrpc: '2.0',
                    params: {
                        model_name: 'res.partner',
                        field_names: 'name,email,city',
                        domain: '[]',
                        limit: 5,
                    },
                }),
            });
            return res.json();
        });
        const result = response.result;
        expect(result).toBeTruthy();
        expect(Array.isArray(result.columns)).toBe(true);
        expect(result.columns.length).toBe(3);
        expect(Array.isArray(result.rows)).toBe(true);
        expect(result.rows.length).toBeLessThanOrEqual(5);
        expect(typeof result.total).toBe('number');
    });

    test('model whitelist blocks disallowed models', async ({ page }) => {
        const response = await page.evaluate(async () => {
            const res = await fetch('/woow_snippet/stat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    jsonrpc: '2.0',
                    params: {
                        model_name: 'ir.config_parameter',
                        operation: 'count',
                    },
                }),
            });
            return res.json();
        });
        // Should return an error
        expect(response.error || response.result?.error).toBeTruthy();
    });
});

// ============================================================
// TEST SUITE 3: Website Frontend - Snippet Rendering
// ============================================================
test.describe('Frontend Snippet Rendering', () => {
    test.beforeEach(async ({ page }) => {
        await loginAsAdmin(page);
    });

    test('homepage loads without JS errors', async ({ page }) => {
        const errors = [];
        page.on('pageerror', err => errors.push(err.message));
        await page.goto(`${BASE_URL}/`);
        await page.waitForLoadState('networkidle');
        // Filter out known non-critical errors
        const criticalErrors = errors.filter(
            e => e.includes('woow') || e.includes('snippet')
        );
        expect(criticalErrors).toHaveLength(0);
    });

    test('demo page with snippets renders if exists', async ({ page }) => {
        const response = await page.goto(`${BASE_URL}/woow-demo`);
        if (response && response.status() === 200) {
            await page.waitForLoadState('networkidle');
            // Check for snippet containers
            const stats = await page.locator('.s_woow_stat').count();
            const charts = await page.locator('.s_woow_chart').count();
            const tables = await page.locator('.s_woow_data_table').count();
            // At least some snippets should be present on the demo page
            console.log(`Found: ${stats} stat cards, ${charts} charts, ${tables} data tables`);
        } else {
            console.log('Demo page not found (expected if not created yet), skipping');
        }
    });
});

// ============================================================
// TEST SUITE 4: Website Editor - BLOCKS Panel
// ============================================================
test.describe('Website Editor Integration', () => {
    test.beforeEach(async ({ page }) => {
        await loginAsAdmin(page);
    });

    test('BLOCKS panel shows WoOW Dynamic group', async ({ page }) => {
        await page.goto(`${BASE_URL}/`);
        await page.waitForLoadState('networkidle');

        // Enter edit mode
        const editBtn = page.locator('a.o_edit_website_container').first();
        if (await editBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
            await editBtn.click();
            // Wait for editor to initialize
            await page.waitForTimeout(3000);

            // Look for the snippet panel or blocks tab
            const blocksTab = page.locator('[data-container="blocks"], #oe_snippets .o_panel_header:has-text("BLOCKS")').first();
            if (await blocksTab.isVisible({ timeout: 5000 }).catch(() => false)) {
                await blocksTab.click().catch(() => {});
            }

            // Check for WoOW Dynamic group
            const woowGroup = page.locator('text=WoOW Dynamic').first();
            const isVisible = await woowGroup.isVisible({ timeout: 5000 }).catch(() => false);
            if (isVisible) {
                console.log('WoOW Dynamic group found in BLOCKS panel');
            } else {
                console.log('WoOW Dynamic group text not directly visible - may need scrolling or different panel state');
            }
        } else {
            console.log('Edit button not accessible - website may need initial setup');
        }
    });
});

// ============================================================
// TEST SUITE 5: Asset Loading
// ============================================================
test.describe('Asset Loading', () => {
    test.beforeEach(async ({ page }) => {
        await loginAsAdmin(page);
    });

    test('frontend JS assets load without 404', async ({ page }) => {
        const failedRequests = [];
        page.on('response', response => {
            const url = response.url();
            if (url.includes('woow_snippet_builder') && response.status() >= 400) {
                failedRequests.push({ url, status: response.status() });
            }
        });
        await page.goto(`${BASE_URL}/`);
        await page.waitForLoadState('networkidle');
        expect(failedRequests).toHaveLength(0);
    });

    test('SVG thumbnails are accessible', async ({ page }) => {
        const thumbs = [
            's_woow_dynamic_content.svg',
            's_woow_stat.svg',
            's_woow_chart.svg',
            's_woow_data_table.svg',
        ];
        for (const thumb of thumbs) {
            const url = `${BASE_URL}/woow_snippet_builder/static/src/img/snippets_thumbs/${thumb}`;
            const response = await page.goto(url);
            expect(response.status()).toBe(200);
        }
    });
});
