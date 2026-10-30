/* This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0. */

/** Send a semantic action through the single validated control boundary. */
async function sendControl(action, arguments_={}) {
    const response = await apiPost('api.controls.dispatch', {action:action, arguments:arguments_});
    return response.result;
}

/** Bind existing and future controls once; normalize mouse, keyboard and rapid touch activation. */
class ControlBindings {
    constructor(root, {onControl=sendControl, onError=reportError}={}) {
        this.root = root;
        this.onControl = onControl;
        this.onError = onError;
        this.abort = new AbortController();
        this.touches = new WeakMap();
        this.lastTap = 0;
        const options = {signal:this.abort.signal};
        root.addEventListener('click', event => {
            const button = this.button(event);
            if (!button) return;
            const touched = this.touches.get(button);
            if (event.detail !== 0 && touched !== undefined && Date.now() - touched < 500) return;
            this.activate(button);
        }, options);
        root.addEventListener('touchstart', event => {
            if (this.button(event) && event.touches.length === 1) event.preventDefault();
        }, {...options, passive:false});
        root.addEventListener('touchend', event => {
            if (event.changedTouches.length !== 1 || event.touches.length) return;
            if (event.target.closest?.('input, select, textarea, a, [contenteditable="true"]')) return;
            const now = Date.now();
            const button = this.button(event);
            if (button) {
                event.preventDefault();
                this.touches.set(button, now);
                this.activate(button);
            }
            else if (now - this.lastTap < 350 && event.cancelable) event.preventDefault();
            this.lastTap = now;
        }, {...options, passive:false});
        for (const type of ['dblclick', 'gesturestart', 'gesturechange']) {
            root.addEventListener(type, event => event.preventDefault(), {...options, passive:false});
        }
    }

    button(event) {
        const button = event.target.closest?.('[data-control]');
        return button && this.root.contains(button) && !button.disabled ? button : null;
    }

    async activate(button) {
        try {
            const arguments_ = JSON.parse(button.dataset.controlArgs || '{}');
            await this.onControl(button.dataset.control, arguments_, button);
        }
        catch (error) { this.onError(error); }
    }

    destroy() { this.abort.abort(); }
}
