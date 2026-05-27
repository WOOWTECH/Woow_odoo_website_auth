/** @odoo-module */
import dynamicSnippetOptions from "@website/snippets/s_dynamic_snippet/options";

/**
 * Extends the native dynamic snippet options to allow all filters (not
 * restricted to a single model).  This gives the WoOW Dynamic Content
 * snippet access to any website.snippet.filter record, regardless of the
 * model it is configured for.
 */
const WoowDynamicContentOptions = dynamicSnippetOptions.extend({
    // Allow all models — don't restrict the filter list
    modelNameFilter: undefined,
});

import options from "@web_editor/js/editor/snippets.options";
options.registry.woow_dynamic_content = WoowDynamicContentOptions;

export default WoowDynamicContentOptions;
