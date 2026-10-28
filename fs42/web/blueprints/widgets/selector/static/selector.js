/* This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0. */
window.app = window.app || {};
app.widgets = app.widgets || {};
app.widgets.selector = (function() {
    let self = {instances: {}};

    class Selector {
        constructor(config) {
            this.element = document.getElementById(config.attributes.id);
        }

        /** Replace available choices while preserving text as display data. */
        setOptions(options, selected) {
            this.element.replaceChildren();
            for (const item of options) {
                const option = document.createElement('option');
                option.value = item.value;
                option.textContent = item.label;
                this.element.appendChild(option);
            }
            if (selected !== undefined) this.element.value = selected;
        }

        getValue() {
            return this.element.value;
        }

        onChange(callback) {
            this.element.addEventListener('change', callback);
        }
    }

    /** Create and register an independent widget instance. */
    self.setup = function(config) {
        const instance = new Selector(config);
        self.instances[config.attributes.id] = instance;
        return instance;
    };
    return self;
})();
