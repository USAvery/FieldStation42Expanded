/* This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0. */
window.app = window.app || {};
app.menu_widgets = app.menu_widgets || {};
app.menu_widgets.menu_clock = (function() {
    let self = {instances: {}};

    class MenuClock {
        constructor(config) {
            this.element = document.getElementById(config.attributes.id);
            if (!this.element) throw new Error('Menu clock element was not found: ' + config.attributes.id);
            this.formatter = new Intl.DateTimeFormat(config.locale, config.options);
            this.compact = config.compact;
            this.timer = null;
            this.render = this.render.bind(this);
        }

        /** Render local time while keeping a machine-readable timestamp on the element. */
        render() {
            if (!this.element.isConnected) {
                this.stop();
                return;
            }
            const now = new Date();
            let text = this.formatter.format(now);
            if (this.compact) text = text.replace(/\s/g, '').toLowerCase();
            this.element.textContent = text;
            this.element.dateTime = now.toISOString();
        }

        /** Render immediately and maintain one update timer for this instance. */
        start() {
            this.stop();
            this.render();
            if (this.element.isConnected) this.timer = setInterval(this.render, 1000);
        }

        stop() {
            if (this.timer !== null) clearInterval(this.timer);
            this.timer = null;
        }
    }

    /** Stop the previous instance before replacing a clock with the same ID. */
    self.setup = function(config) {
        const id = config.attributes.id;
        if (self.instances[id]) self.instances[id].stop();
        const clock = new MenuClock(config);
        self.instances[id] = clock;
        clock.start();
        window.removeEventListener('beforeunload', self.cleanUp);
        window.addEventListener('beforeunload', self.cleanUp);
        return clock;
    };

    self.cleanUp = function() {
        for (const clock of Object.values(self.instances)) clock.stop();
        self.instances = {};
    };

    return self;
})();
