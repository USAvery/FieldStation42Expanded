/* This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0. */
window.app = window.app || {};
app.widgets = app.widgets || {};
app.widgets.log_display = (function() {
    let self = {instances: {}};
    self.setup = function(config) {
        const prefix = config.prefix;
        const frame = document.getElementById(prefix + '-log-frame');
        const content = document.getElementById(prefix + '-log');
        const instance = {
            show: function(message) { content.textContent = message; frame.style.display = ''; },
            hide: function() { frame.style.display = 'none'; }
        };
        document.getElementById(prefix + '-log-dismiss').onclick = instance.hide;
        self.instances[prefix] = instance;
        return instance;
    };
    return self;
})();
