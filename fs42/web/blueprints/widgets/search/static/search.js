/* This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0. */
window.app = window.app || {};
app.widgets = app.widgets || {};
app.widgets.search = (function() {
    let self = {instances: {}};

    class Search {
        constructor(config) {
            this.config = config;
            this.input = document.getElementById(config.id + '-input');
            this.submit = document.getElementById(config.id + '-btn');
            this.clear = document.getElementById('clear-' + config.id + '-btn');
            this.onKeydown = this.onKeydown.bind(this);
        }

        /** Bind this instance's search and reset actions. */
        bind(search, reset) {
            this.search = search;
            this.submit.onclick = search;
            this.clear.onclick = reset;
            this.input.onkeydown = this.onKeydown;
        }

        onKeydown(event) {
            if (event.key === 'Enter') {
                event.preventDefault();
                this.search();
            }
        }

        busy(value) {
            this.submit.disabled = value;
            this.submit.textContent = value ? this.config.loading : 'Search';
        }

        message(text) {
            document.getElementById(this.config.id + '-results-content').textContent = text;
            document.getElementById(this.config.id + '-results').style.display = '';
        }
    }

    /** Create and register an independent widget instance. */
    self.setup = function(config) {
        const instance = new Search(config);
        self.instances[config.id] = instance;
        return instance;
    };
    return self;
})();
