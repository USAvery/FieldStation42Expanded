/*
This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
See https://mozilla.org/MPL/2.0/.
*/
window.app = window.app || {};
app.web_interface = app.web_interface || {};
app.web_interface.handheld_remote = (function () {
    let self = {};
    let entry_buffer = '';
    let entry_timer = null;
    let bindings = null;
    let status_timer = null;

    self.localActions = {
        'remote.digit': function({digit}) { self.appendDigit(digit); },
        'remote.clear': function() { self.clearEntry(); },
        'remote.submit': function() { return self.sendDirect(true); }
    };
    self.handleControl = async function(action, arguments_={}) {
        if (Object.hasOwn(self.localActions, action)) return self.localActions[action](arguments_);
        const result = await sendControl(action, arguments_);
        if (result?.channel !== undefined) self.updateStatusDisplay(result);
        else self.updateStatus();
        return result;
    };
    self.appendDigit = function(n) {
        if (entry_buffer.length >= 2) entry_buffer = '';
        entry_buffer += n.toString();
        document.getElementById('entry').innerText = entry_buffer;
        if (entry_timer) clearTimeout(entry_timer);
        entry_timer = setTimeout(function () {
            self.sendDirect(false);
        }, 1500);
    };
    self.clearEntry = function() {
        entry_buffer = '';
        document.getElementById('entry').innerText = '_';
        if (entry_timer) clearTimeout(entry_timer);
    };
    self.sendDirect = async function(force) {
        const channel = parseInt(entry_buffer, 10);
        if (force || entry_buffer.length > 0) self.clearEntry();
        if (!Number.isNaN(channel)) {
            try { await self.handleControl('channel.tune', {channel:channel}); }
            catch (error) { reportError(error); }
        }
    };
    self.updateStatusDisplay = function(data) {
        if (data.channel != null && data.channel >= 1) {
            document.getElementById('current-channel').innerText = data.channel.toString().padStart(2, '0');
        }
        else {
            document.getElementById('current-channel').innerText = '--';
        }
        document.getElementById('network-name').innerText = data.name || '';
        document.getElementById('title').innerText = data.title || ''; // Added this line
    };
    self.updateStatus = function() {
        fetchURL('api.remote_control.get_status')
            .then(function (response) {
                return response.json();
            })
            .then(self.updateStatusDisplay).catch(reportError);
    };
    self.cleanUp = function() {
        bindings?.destroy();
        bindings = null;
        if (status_timer !== null) clearInterval(status_timer);
        if (entry_timer !== null) clearTimeout(entry_timer);
        status_timer = entry_timer = null;
    };

    self.setup = function() {
        self.cleanUp();
        bindings = new ControlBindings(document, {onControl:self.handleControl});
        status_timer = setInterval(self.updateStatus, 2000);
        self.updateStatus();
        window.addEventListener('beforeunload', self.cleanUp);
    };
    return self;
})();
