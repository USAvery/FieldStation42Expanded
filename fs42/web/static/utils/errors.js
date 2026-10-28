/* This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0. */
window.app = window.app || {};
app.utils = app.utils || {};
app.utils.errors = (function() {
    let self = {};
    /** Return a consistent explanation for network, validation, and server errors. */
    self.message = function(error) {
        const detail = error && (error.detail || error.message || error.error);
        if (Array.isArray(detail)) {
            return detail.map(item => typeof item === 'string' ? item : (item.loc || []).join('.') + ': ' + item.msg).join('\n');
        }
        return typeof detail === 'string' ? detail : 'An unexpected error occurred. Please try again.';
    };
    /** Write an error as text so server messages cannot introduce page markup. */
    self.show = function(element, error) {
        const target = typeof element === 'string' ? document.getElementById(element) : element;
        target.textContent = self.message(error);
        target.setAttribute('role', 'alert');
        target.hidden = false;
        target.style.display = '';
    };
    /** Present a page-level failure through the common accessible notice. */
    self.report = function(error) {
        let target = document.getElementById('app-errors');
        if (!target) {
            target = document.createElement('div');
            target.id = 'app-errors';
            document.body.prepend(target);
        }
        self.show(target, error);
    };
    return self;
})();
