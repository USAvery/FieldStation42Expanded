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
    self.sendCommand = function(cmd) {
        fetchURL('api.remote_control.handle_command', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                command: cmd,
                channel: -1
            })
        })
            .then(function (response) {
                return response.json();
            })
            .then(function (data) {
                console.log('Sent:', cmd, data);
                self.updateStatusDisplay(data.current);
            }).catch(reportError);
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
    self.sendDirect = function(force) {
        const chan = parseInt(entry_buffer, 10);
        if (!isNaN(chan)) {
            fetchURL('api.remote_control.handle_command', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    command: 'direct',
                    channel: chan
                })
            }).then(function () {
                console.log('Sent direct', chan);
                self.updateStatus();
            });
        }
        if (force || entry_buffer.length > 0) self.clearEntry();
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
    /** Prevent rapid remote presses from zooming the page. */
    self.preventZoom = function(event) {
        event.preventDefault();
    };

    self.setup = function () {
        setInterval(self.updateStatus, 2000);
        self.updateStatus();

        /* Keep rapid remote-button taps from triggering browser double-tap zoom. */
        for (const button of document.querySelectorAll('.btn')) {
            button.addEventListener('dblclick', self.preventZoom);
        }
    };
    /**
     * Open the television's On Demand menu without changing the tuned channel
     */
    self.openOnDemand = function() {
        self.clearEntry();
        self.sendCommand('on_demand_menu');
    };
    return self;
})();
