/*
This Source Code Form is subject to the Mozilla Public License, v. 2.0.
See https://mozilla.org/MPL/2.0/.
*/
window.app = window.app || {};
app.web_interface = app.web_interface || {};
app.web_interface.about = (function () {
    let self = {};

    self.loadThemes = async function() {
        try {
            const response = await fetchURL('api.themes.get_themes');
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
            reportError(e);
        }
    };
    /**
     * Init Theme
     */
    self.initTheme = function() {
        const saved_theme = localStorage.getItem('fs42-theme') || 'default';
        self.setTheme(saved_theme);
        self.loadThemes();
    };
    /**
     * Set Theme
     */
    self.setTheme = function(theme_name) {
        const theme_link = document.getElementById('theme-css');
        theme_link.href = urlFor('/static/themes/' + theme_name + '.css');
        localStorage.setItem('fs42-theme', theme_name);
    };
    /**
     * Toggle Auto Scroll
     */
    self.toggleAutoScroll = function(enabled) {
        localStorage.setItem('fs42-autoscroll', enabled ? 'true' : 'false');
    };
    /**
     * Init Auto Scroll Checkbox
     */
    self.initAutoScrollCheckbox = function() {
        const checkbox = document.getElementById('autoscroll-checkbox');
        if (checkbox) {
            const saved_setting = localStorage.getItem('fs42-autoscroll');
            checkbox.checked = saved_setting !== 'false'; // Default to true if not set
        }
    };

    /** Bind page controls and load the initial data. */
    self.setup = async function() {
        /**
         * Load Themes
         */
        // Theme management

        // Load themes for the rendered selector
        self.initTheme();

        // Initialize auto-scroll checkbox
        self.initAutoScrollCheckbox();
    };
    return self;
})();
