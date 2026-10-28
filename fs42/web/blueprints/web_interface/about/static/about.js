/*
This Source Code Form is subject to the Mozilla Public License, v. 2.0.
See https://mozilla.org/MPL/2.0/.
*/
window.app = window.app || {};
app.web_interface = app.web_interface || {};
app.web_interface.about = (function () {
    let self = {};

    async function loadThemes() {
        try {
            const response = await window.fs42Api.fetch('api.themes.get_themes');
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
            app.utils.errors.report(e);
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
        theme_link.href = window.fs42Api.urlFor('/static/themes/' + theme_name + '.css');
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

    /** Bind page controls and load the initial data. */
    self.setup = async function() {
        /**
         * Load Themes
         */
        // Theme management

        // Load themes for the rendered selector
        initTheme();

        // Initialize auto-scroll checkbox
        initAutoScrollCheckbox();
    };
    Object.assign(self, {
        loadThemes, initTheme, setTheme, toggleAutoScroll, initAutoScrollCheckbox
    });
    return self;
})();
