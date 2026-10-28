/*
This Source Code Form is subject to the Mozilla Public License, v. 2.0.
See https://mozilla.org/MPL/2.0/.
*/
window.app = window.app || {};
app.web_interface = app.web_interface || {};
app.web_interface.guide = (function() {
    let self = {};

    /**
     * Reflect the guide frame's file-name preference in the toggle
     */
    self.render = function() {
        const control = document.querySelector('.debug-toggle');
        const enabled = localStorage.getItem('fs42-guide-debug') === 'true';
        control.querySelector('input').checked = enabled;
        control.classList.toggle('is-on', enabled);
    };

    /**
     * Update the embedded guide when the preference changes
     */
    self.onChange = function(event) {
        const frame = document.getElementById('guide-frame');
        const win = frame && frame.contentWindow;
        const enabled = event.target.checked;
        localStorage.setItem('fs42-guide-debug', String(enabled));
        if (win && typeof win.setDebugFilename === 'function') {
            win.setDebugFilename(enabled);
        }
        self.render();
    };

    /**
     * Bind the controls rendered by the guide template
     */
    self.setup = function() {
        document.querySelector('.debug-toggle-input').addEventListener('change', self.onChange);
        self.render();
    };

    return self;
})();
