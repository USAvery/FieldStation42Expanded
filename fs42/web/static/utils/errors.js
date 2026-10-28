/* This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0. */
/** Return a consistent explanation for network, validation, and server errors. */
function errorMessage(error) {
    const detail = error && (error.detail || error.message || error.error);
    if (Array.isArray(detail)) {
        return detail.map(item => typeof item === 'string' ? item : (item.loc || []).join('.') + ': ' + item.msg).join('\n');
    }
    return typeof detail === 'string' ? detail : 'An unexpected error occurred. Please try again.';
}
/** Write an error as text so server messages cannot introduce page markup. */
function showError(element, error) {
    const target = typeof element === 'string' ? document.getElementById(element) : element;
    target.textContent = errorMessage(error);
    target.setAttribute('role', 'alert');
    target.hidden = false;
    target.style.display = '';
}
/** Present a page-level failure through the common accessible notice. */
function reportError(error) {
    let target = document.getElementById('app-errors');
    if (!target) {
        target = document.createElement('div');
        target.id = 'app-errors';
        document.body.prepend(target);
    }
    showError(target, error);
}
