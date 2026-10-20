/*
This Source Code Form is subject to the Mozilla Public License, v. 2.0.
See https://mozilla.org/MPL/2.0/.
*/
window.app = window.app || {};
app.tools = app.tools || {};
app.tools.about = (function () {
    let self = {};
    /**
     * Set up the about page
     */
    self.setup = function () {
        /**
         * Load Themes
         */
        // Theme management
        async function loadThemes() {
            try {
                const response = await fetch('/about/themes');
                const data = await response.json();
                const select = document.getElementById('theme-select');
                select.innerHTML = '';
                data.themes.forEach(function (theme) {
                    const option = document.createElement('option');
                    option.value = theme.id;
                    option.textContent = theme.name;
                    select.appendChild(option);
                });

                // Set the current theme
                const saved_theme = localStorage.getItem('fs42-theme') || 'default';
                select.value = saved_theme;
            }
            catch (e) {
                console.error('Error loading themes:', e);
            }
        }
        /**
         * Init Theme
         */
        function initTheme() {
            const saved_theme = localStorage.getItem('fs42-theme') || 'default';
            setTheme(saved_theme);
            loadThemes();
        }
        /**
         * Set Theme
         */
        function setTheme(theme_name) {
            const theme_link = document.getElementById('theme-css');
            theme_link.href = '/static/themes/' + theme_name + '.css';
            localStorage.setItem('fs42-theme', theme_name);
        }
        /**
         * Toggle Auto Scroll
         */
        function toggleAutoScroll(enabled) {
            localStorage.setItem('fs42-autoscroll', enabled ? 'true' : 'false');
        }
        /**
         * Init Auto Scroll Checkbox
         */
        function initAutoScrollCheckbox() {
            const checkbox = document.getElementById('autoscroll-checkbox');
            if (checkbox) {
                const saved_setting = localStorage.getItem('fs42-autoscroll');
                checkbox.checked = saved_setting !== 'false'; // Default to true if not set
            }
        }

        // Initialize page layout
        document.addEventListener('DOMContentLoaded', async function () {
            initTheme();
            const content = [
                '',
                '        <div class="pure-u-1 pure-u-md-1-2">',
                '            <h2>Application Settings</h2>',
                '            <div class="settings-section">',
                '                <h3>Theme Selection</h3>',
                '                <p>Choose your preferred visual theme for FieldStation42:</p>',
                '                <div class="theme-selector">',
                '                    <select id="theme-select" class="pure-input-1-2" onchange="app.tools.about.setTheme(this.value)">',
                '                        <option>Loading themes...</option>',
                '                    </select>',
                '                </div>',
                '            </div>',
                '            <div class="settings-section" style="margin-top: 2em;">',
                '                <h3>Guide Auto-Scroll</h3>',
                '                <p>Enable or disable automatic scrolling in the TV Guide:</p>',
                '                <div style="margin-top: 1em;">',
                '                    <label style="display: inline-flex; align-items: center; gap: 0.5em; cursor: pointer; user-select: none;">',
                '                        <input type="checkbox" id="autoscroll-checkbox" onchange="app.tools.about.toggleAutoScroll(this.checked)" style="width: 18px; height: 18px; cursor: pointer; margin: 0; flex-shrink: 0;">',
                '                        <span style="line-height: 18px;">Enable auto-scroll</span>',
                '                    </label>',
                '                </div>',
                '            </div>',
                '        </div>',
                '',
                '        <div class="pure-u-1" style="margin-top: 2em;">',
                '            <h2>About FieldStation42</h2>',
                '            <p>FieldStation42 is a modern system that simulates retro TV.</p>',
                '',
                '            <h3>Features</h3>',
                '            <ul>',
                '                <li>Multi-channel management</li>',
                '                <li>Content cataloging and organization</li>',
                '                <li>Schedule planning and automation</li>',
                '                <li>Real-time monitoring and control</li>',
                '            </ul>',
                '',
                '            <h3>System Information</h3>',
                '            <table class="pure-table pure-table-horizontal">',
                '                <tbody>',
                '                    <tr>',
                '                        <td><strong>Version</strong></td>',
                '                        <td>0.1.0</td>',
                '                    </tr>',
                '                    <tr>',
                '                        <td><strong>License</strong></td>',
                '                        <td>Mozilla Public License</td>',
                '                    </tr>',
                '                    <tr>',
                '                        <td><strong>Author</strong></td>',
                '                        <td>Shane Mason</td>',
                '                    </tr>',
                '                </tbody>',
                '            </table>',
                '        </div>',
                '    '
            ].join('\n');
            document.body.innerHTML = await window.fs42Common.createPageLayout('About FieldStation42', content);

            // Load themes after the HTML is inserted
            loadThemes();

            // Initialize auto-scroll checkbox
            initAutoScrollCheckbox();
        });
        self.loadThemes = loadThemes;
        self.initTheme = initTheme;
        self.setTheme = setTheme;
        self.toggleAutoScroll = toggleAutoScroll;
        self.initAutoScrollCheckbox = initAutoScrollCheckbox;
    };
    return self;
})();
