/* This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0. */
window.app = window.app || {};
app.widgets = app.widgets || {};
app.widgets.log_display = (function() {
    let self = {instances: {}};

    class LogDisplay {
        constructor(config) {
            this.frame = document.getElementById(config.prefix + '-log-frame');
            this.content = document.getElementById(config.prefix + '-log');
            this.hide = this.hide.bind(this);
            document.getElementById(config.prefix + '-log-dismiss').onclick = this.hide;
        }

        show(message) {
            this.content.textContent = message;
            this.frame.style.display = '';
        }

        hide() {
            this.frame.style.display = 'none';
        }
    }

    /** Create and register an independent widget instance. */
    self.setup = function(config) {
        const instance = new LogDisplay(config);
        self.instances[config.prefix] = instance;
        return instance;
    };
    return self;
})();
