/*
This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
See https://mozilla.org/MPL/2.0/.
*/
window.app = window.app || {};
app.tools = app.tools || {};
app.tools.handheld_remote = (function () {
    let self = {};
    let entry_buffer = '';
    let entry_timer = null;
    function sendCommand(cmd) {
        fetch('/api/command', {
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
                updateStatusDisplay(data.current);
            });
    }
    function appendDigit(n) {
        if (entry_buffer.length >= 2) entry_buffer = '';
        entry_buffer += n.toString();
        document.getElementById('entry').innerText = entry_buffer;
        if (entry_timer) clearTimeout(entry_timer);
        entry_timer = setTimeout(function () {
            sendDirect(false);
        }, 1500);
    }
    function clearEntry() {
        entry_buffer = '';
        document.getElementById('entry').innerText = '_';
        if (entry_timer) clearTimeout(entry_timer);
    }
    function sendDirect(force) {
        const chan = parseInt(entry_buffer, 10);
        if (!isNaN(chan)) {
            fetch('/api/command', {
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
                updateStatus();
            });
        }
        if (force || entry_buffer.length > 0) clearEntry();
    }
    function updateStatusDisplay(data) {
        if (data.channel != null && data.channel >= 1) {
            document.getElementById('current-channel').innerText = data.channel.toString().padStart(2, '0');
        }
        else {
            document.getElementById('current-channel').innerText = '--';
        }
        document.getElementById('network-name').innerText = data.name || '';
        document.getElementById('title').innerText = data.title || ''; // Added this line
    }
    function updateStatus() {
        fetch('/api/status')
            .then(function (response) {
                return response.json();
            })
            .then(updateStatusDisplay);
    }
    self.setup = function () {
        setInterval(updateStatus, 2000);
        updateStatus();

        /* Keep rapid remote-button taps from triggering browser double-tap zoom. */
        document.querySelectorAll('.btn').forEach(function (button) {
            button.addEventListener('dblclick', function (event) {
                event.preventDefault();
            });
        });
    };
    self.sendCommand = sendCommand;
    self.appendDigit = appendDigit;
    self.clearEntry = clearEntry;
    self.sendDirect = sendDirect;
    return self;
})();
