/* This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0. */
window.app = window.app || {};
app.widgets = app.widgets || {};
app.widgets.search = (function() {
    let self = {instances: {}};
    self.setup = function(config) {
        const id = config.id;
        const input = document.getElementById(id + '-input');
        const submit = document.getElementById(id + '-btn');
        const clear = document.getElementById('clear-' + id + '-btn');
        const instance = {
            bind: function(search, reset) {
                submit.onclick = search;
                clear.onclick = reset;
                input.onkeydown = function(event) {
                    if (event.key === 'Enter') { event.preventDefault(); search(); }
                };
            },
            busy: function(value) { submit.disabled = value; submit.textContent = value ? config.loading : 'Search'; },
            message: function(text) {
                const results = document.getElementById(id + '-results-content');
                results.textContent = text;
                document.getElementById(id + '-results').style.display = '';
            }
        };
        self.instances[id] = instance;
        return instance;
    };
    return self;
})();
