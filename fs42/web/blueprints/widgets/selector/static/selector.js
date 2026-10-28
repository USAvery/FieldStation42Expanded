/* This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0. */
window.app = window.app || {};
app.widgets = app.widgets || {};
app.widgets.selector = (function() {
    let self = {instances: {}};
    self.setup = function(config) {
        const id = config.attributes.id;
        const element = document.getElementById(id);
        const instance = {
            setOptions: function(options, selected) {
                element.replaceChildren();
                for (const item of options) {
                    const option = document.createElement('option');
                    option.value = item.value;
                    option.textContent = item.label;
                    element.appendChild(option);
                }
                if (selected !== undefined) element.value = selected;
            },
            getValue: function() { return element.value; },
            onChange: function(callback) { element.addEventListener('change', callback); }
        };
        self.instances[id] = instance;
        return instance;
    };
    return self;
})();
