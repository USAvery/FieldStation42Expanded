/*
This Source Code Form is subject to the Mozilla Public License, v. 2.0.
See https://mozilla.org/MPL/2.0/.
*/
window.app = window.app || {};
app.tools = app.tools || {};
app.tools.station_editor = (function () {
    let self = {};
    /**
     * Set up the station editor page
     */
    self.setup = function () {
        let editor = null;
        let station_name = null;
        let is_dirty = false;
        let original_content = '';
        let is_create_mode = false;
        document.addEventListener('DOMContentLoaded', async function () {
            window.fs42Common.initTheme();

            // Get parameters from URL
            const params = new URLSearchParams(window.location.search);
            const mode = params.get('mode');
            station_name = params.get('station');

            // Check if we're in create mode
            is_create_mode = mode === 'create';
            if (!is_create_mode && !station_name) {
                alert('No station specified');
                window.location.href = '/static/stations.html';
                return;
            }
            const header_title = is_create_mode ? 'Create New Station' : 'Edit Station Configuration';
            const header_subtitle = is_create_mode ? 'Configure your new channel' : escapeHtml(station_name);
            const content =
                '\n        <div class="editor-header">\n            <div>\n                <h1 style="margin:0;">' +
                header_title +
                '</h1>\n                <p style="color:#8b949e;margin:0.5em 0 0 0;">' +
                header_subtitle +
                [
                    '</p>',
                    '            </div>',
                    '            <a href="/static/stations.html" class="pure-button">',
                    '                ← Back to Stations',
                    '            </a>',
                    '        </div>',
                    '',
                    '        <div id="editor-container"></div>',
                    '',
                    '        <div id="error-panel">',
                    '            <div class="error-header">⚠️ Validation Errors</div>',
                    '            <div id="error-list"></div>',
                    '        </div>',
                    '',
                    '        <div id="success-message" class="success-message">',
                    '            ✓ Configuration saved successfully!',
                    '        </div>',
                    '',
                    '        <div class="editor-actions">',
                    '            <button id="save-btn" class="pure-button pure-button-primary" onclick="app.tools.station_editor.saveStation()">',
                    '                Save',
                    '            </button>',
                    '            <button class="pure-button" onclick="app.tools.station_editor.cancelEdit()">',
                    '                Cancel',
                    '            </button>',
                    '            <button id="format-btn" class="pure-button" onclick="app.tools.station_editor.formatDocument()">',
                    '                Format JSON',
                    '            </button>',
                    '        </div>',
                    '    '
                ].join('\n');
            document.body.innerHTML = await window.fs42Common.createPageLayout('', content);

            // Initialize Monaco Editor
            await initEditor();

            // Load station config or template
            if (is_create_mode) {
                await loadTemplate();
            }
            else {
                await loadStation();
            }
        });
        /**
         * Init Editor
         */
        async function initEditor() {
            return new Promise(function (resolve) {
                require.config({
                    paths: {
                        vs: 'https://cdn.jsdelivr.net/npm/monaco-editor@0.44.0/min/vs'
                    }
                });
                require(['vs/editor/editor.main'], function () {
                    // Define custom theme matching FieldStation42 dark theme
                    monaco.editor.defineTheme('fs42-dark', {
                        base: 'vs-dark',
                        inherit: true,
                        rules: [],
                        colors: {
                            'editor.background': '#0d1117',
                            'editor.foreground': '#e6e6e6',
                            'editorLineNumber.foreground': '#8b949e',
                            'editorLineNumber.activeForeground': '#61afef',
                            'editor.selectionBackground': '#1f6feb40',
                            'editor.inactiveSelectionBackground': '#1f6feb20'
                        }
                    });
                    editor = monaco.editor.create(document.getElementById('editor-container'), {
                        value: '// Loading...',
                        language: 'json',
                        theme: 'fs42-dark',
                        automaticLayout: true,
                        lineNumbers: 'on',
                        minimap: {
                            enabled: true
                        },
                        scrollBeyondLastLine: false,
                        formatOnPaste: false,
                        formatOnType: false,
                        tabSize: 2,
                        insertSpaces: true
                    });

                    // Track changes for dirty state
                    editor.onDidChangeModelContent(function () {
                        is_dirty = editor.getValue() !== original_content;
                        updateSaveButton();
                    });
                    resolve();
                });
            });
        }
        /**
         * Compact Json Stringify
         */
        function compactJsonStringify(obj, indent = 4) {
            // Custom JSON formatter for more compact output
            // Keeps simple objects on one line, expands complex ones
            const indent_str = ' '.repeat(indent);
            /**
             * Format
             */
            function format(val, depth = 0) {
                const current_indent = indent_str.repeat(depth);
                const next_indent = indent_str.repeat(depth + 1);
                if (val === null) {
                    return 'null';
                }
                if (typeof val === 'boolean') {
                    return val.toString();
                }
                if (typeof val === 'number') {
                    return val.toString();
                }
                if (typeof val === 'string') {
                    return JSON.stringify(val);
                }
                if (Array.isArray(val)) {
                    if (val.length === 0) {
                        return '[]';
                    }
                    // Keep simple arrays compact
                    if (
                        val.every(function (v) {
                            return typeof v !== 'object' || v === null;
                        })
                    ) {
                        return (
                            '[' +
                            val
                                .map(function (v) {
                                    return format(v, depth);
                                })
                                .join(', ') +
                            ']'
                        );
                    }
                    // Expand complex arrays
                    return (
                        '[\n' +
                        val
                            .map(function (v) {
                                return next_indent + format(v, depth + 1);
                            })
                            .join(',\n') +
                        '\n' +
                        current_indent +
                        ']'
                    );
                }
                if (typeof val === 'object') {
                    const keys = Object.keys(val);
                    if (keys.length === 0) {
                        return '{}';
                    }

                    // Check if object is simple (no nested objects/arrays, max 3 properties)
                    const is_simple =
                        keys.length <= 3 &&
                        keys.every(function (k) {
                            const v = val[k];
                            return v === null || typeof v !== 'object';
                        });
                    if (is_simple) {
                        return (
                            '{' +
                            keys
                                .map(function (k) {
                                    return JSON.stringify(k) + ': ' + format(val[k], depth);
                                })
                                .join(', ') +
                            '}'
                        );
                    }

                    // Expand complex objects
                    return (
                        '{\n' +
                        keys
                            .map(function (k) {
                                return next_indent + JSON.stringify(k) + ': ' + format(val[k], depth + 1);
                            })
                            .join(',\n') +
                        '\n' +
                        current_indent +
                        '}'
                    );
                }
                return JSON.stringify(val);
            }
            return format(obj);
        }
        /**
         * Load Station
         */
        async function loadStation() {
            try {
                const data = await window.fs42Api.get('stations/' + encodeURIComponent(station_name));

                // Load the config using compact formatting
                const json_str = compactJsonStringify(data.station_config, 4);
                original_content = json_str;
                editor.setValue(json_str);
                is_dirty = false;
                updateSaveButton();
            }
            catch (error) {
                showError('Failed to load station: ' + (error.message || 'Unknown error'));
            }
        }
        /**
         * Load Template
         */
        async function loadTemplate() {
            try {
                // Get template from sessionStorage
                const template_str = sessionStorage.getItem('newStationTemplate');
                if (!template_str) {
                    throw new Error('No template found in session');
                }

                // Clear from sessionStorage
                sessionStorage.removeItem('newStationTemplate');

                // Parse and load the template
                const template = JSON.parse(template_str);
                const json_str = compactJsonStringify(template, 4);
                original_content = ''; // No original content for new stations
                editor.setValue(json_str);
                is_dirty = true; // Mark as dirty since it's new
                updateSaveButton();
            }
            catch (error) {
                showError('Failed to load template: ' + (error.message || 'Unknown error'));
                // Redirect back to dashboard on error
                setTimeout(function () {
                    window.location.href = '/static/stations.html';
                }, 2000);
            }
        }
        /**
         * Save Station
         */
        async function saveStation() {
            // Clear previous messages
            hideError();
            hideSuccess();

            // 1. Validate JSON syntax
            let config;
            try {
                config = JSON.parse(editor.getValue());
            }
            catch (e) {
                showError('Invalid JSON: ' + e.message);
                return;
            }

            // 2. Basic validation
            if (!config.station_conf) {
                showError('Configuration must have a "station_conf" object');
                return;
            }
            if (!config.station_conf.network_name) {
                showError('Missing required field: network_name');
                return;
            }
            if (config.station_conf.channel_number === undefined) {
                showError('Missing required field: channel_number');
                return;
            }

            // 3. Send to API
            try {
                let result;
                if (is_create_mode) {
                    // Create new station with POST
                    result = await window.fs42Api.post('stations', config);

                    // After successful creation, switch to edit mode
                    station_name = config.station_conf.network_name;
                    is_create_mode = false;

                    // Update URL to edit mode
                    const new_url = new URL(window.location.href);
                    new_url.searchParams.delete('mode');
                    new_url.searchParams.set('station', station_name);
                    window.history.replaceState({}, '', new_url);

                    // Update the header
                    document.querySelector('.editor-header h1').textContent = 'Edit Station Configuration';
                    document.querySelector('.editor-header p').textContent = station_name;
                }
                else {
                    // Update existing station with PUT
                    result = await window.fs42Api.put('stations/' + encodeURIComponent(station_name), config);

                    // If the station was renamed, update the URL and station name
                    if (config.station_conf.network_name !== station_name) {
                        station_name = config.station_conf.network_name;
                        const new_url = new URL(window.location.href);
                        new_url.searchParams.set('station', station_name);
                        window.history.replaceState({}, '', new_url);

                        // Update the header
                        document.querySelector('.editor-header p').textContent = station_name;
                    }
                }

                // Success!
                original_content = editor.getValue();
                is_dirty = false;
                updateSaveButton();
                showSuccess();
            }
            catch (error) {
                // Server validation error
                let error_msg = error.detail || error.message || 'Failed to save configuration';

                // Try to parse and enhance schema validation errors
                error_msg = enhanceErrorMessage(error_msg);
                showError(error_msg);

                // Try to highlight the field mentioned in the error
                highlightErrorField(error_msg);
            }
        }
        /**
         * Format Document
         */
        function formatDocument() {
            try {
                // Parse current editor content
                const current_json = JSON.parse(editor.getValue());

                // Format using our compact formatter
                const formatted = compactJsonStringify(current_json, 4);

                // Update editor
                editor.setValue(formatted);

                // Mark as dirty since we changed the content
                is_dirty = formatted !== original_content;
                updateSaveButton();
            }
            catch (e) {
                showError('Cannot format: ' + e.message);
            }
        }
        /**
         * Cancel Edit
         */
        function cancelEdit() {
            if (is_dirty && !confirm('You have unsaved changes. Are you sure you want to leave?')) {
                return;
            }
            window.location.href = '/static/stations.html';
        }
        /**
         * Update Save Button
         */
        function updateSaveButton() {
            const btn = document.getElementById('save-btn');
            btn.disabled = !is_dirty;
            btn.textContent = is_dirty ? 'Save *' : 'Save';
        }
        /**
         * Show Error
         */
        function showError(message) {
            const panel = document.getElementById('error-panel');
            const list = document.getElementById('error-list');
            if (typeof message === 'string') {
                list.innerHTML = '<div class="error-item">' + escapeHtml(message) + '</div>';
            }
            else if (Array.isArray(message)) {
                list.innerHTML = message
                    .map(function (err) {
                        return '<div class="error-item">' + escapeHtml(err) + '</div>';
                    })
                    .join('');
            }
            panel.classList.add('visible');
        }
        /**
         * Hide Error
         */
        function hideError() {
            document.getElementById('error-panel').classList.remove('visible');
        }
        /**
         * Show Success
         */
        function showSuccess() {
            const msg = document.getElementById('success-message');
            msg.classList.add('visible');

            // Hide after 3 seconds
            setTimeout(function () {
                msg.classList.remove('visible');
            }, 3000);
        }
        /**
         * Hide Success
         */
        function hideSuccess() {
            document.getElementById('success-message').classList.remove('visible');
        }
        /**
         * Enhance Error Message
         */
        function enhanceErrorMessage(error_msg) {
            // Just return the original server error message as-is
            return error_msg;
        }
        /**
         * Highlight Error Field
         */
        function highlightErrorField(error_msg) {
            // Don't try to highlight - server errors don't include line numbers
            // Just clear any previous markers
            monaco.editor.setModelMarkers(editor.getModel(), 'validation', []);
        }
        /**
         * Escape Html
         */
        function escapeHtml(text) {
            if (!text) {
                return '';
            }
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        // Warn before leaving with unsaved changes
        window.addEventListener('beforeunload', function (e) {
            if (is_dirty) {
                e.preventDefault();
                e.returnValue = 'You have unsaved changes. Are you sure you want to leave?';
            }
        });
        self.initEditor = initEditor;
        self.compactJsonStringify = compactJsonStringify;
        self.loadStation = loadStation;
        self.loadTemplate = loadTemplate;
        self.saveStation = saveStation;
        self.formatDocument = formatDocument;
        self.cancelEdit = cancelEdit;
        self.updateSaveButton = updateSaveButton;
        self.showError = showError;
        self.hideError = hideError;
        self.showSuccess = showSuccess;
        self.hideSuccess = hideSuccess;
        self.enhanceErrorMessage = enhanceErrorMessage;
        self.highlightErrorField = highlightErrorField;
        self.escapeHtml = escapeHtml;
    };
    return self;
})();
