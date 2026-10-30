/*
This Source Code Form is subject to the Mozilla Public License, v. 2.0.
See https://mozilla.org/MPL/2.0/.
*/
window.app = window.app || {};
app.web_interface = app.web_interface || {};
app.web_interface.remote = (function () {
    let self = {};

    let display = null;
    let now_playing_network = null;
    let now_playing_status = null;
    let now_playing_title = null;
    let current_channel = '001';
    let status_poll_interval = null;
    let status_epoch = 0;
    let status_pending = false;
    let channel_input = '';
    let channel_input_timeout = null;
    let is_inputting_channel = false;
    let volume_display_timeout = null;
    let is_showing_volume = false;
    let info_mode = 'playing'; // 'playing' or 'system'
    let pad_mode = 'number'; // 'number' or 'nav'
    let awaiting_pin = false;
    let pin_digits_entered = 0;
    let number_pad = null;
    let nav_pad = null;
    /**
     * Idle Display Text
     */
    self.idleDisplayText = function() {
        if (awaiting_pin) {
            return pin_digits_entered > 0 ? '•'.repeat(pin_digits_entered) : 'ENTER PIN';
        }
        return 'CH ' + current_channel;
    };
    /**
     * Update Now Playing From Status
     */
    self.updateNowPlayingFromStatus = function(status) {
        awaiting_pin = !!status.awaiting_pin;
        pin_digits_entered = status.pin_digits_entered || 0;
        if (info_mode === 'playing') {
            if (status.status === 'playing') {
                // Top line: "Playing"
                now_playing_network.textContent = 'Playing';
                // Second line: network_name
                now_playing_status.textContent = status.network_name || '';
                // Third line: title
                now_playing_title.textContent = status.title || '';

                // Update channel display and current channel to match actual channel
                // BUT only if we're not currently inputting a channel number or showing volume
                if (status.channel_number && status.channel_number > 0) {
                    current_channel = String(status.channel_number).padStart(3, '0');
                    if (!is_inputting_channel && !is_showing_volume && feedback_timeout === null) {
                        display.textContent = self.idleDisplayText();
                    }
                }
            }
            else if (status.status === 'stopped') {
                now_playing_network.textContent = 'Stopped';
                now_playing_status.textContent = '';
                now_playing_title.textContent = '';
                if (!is_inputting_channel && !is_showing_volume && feedback_timeout === null) {
                    display.textContent = 'STOPPED';
                }
            }
            else if (status.status === 'idle') {
                // The player hands back from parental controls as 'idle' and
                // starts playing a moment later - a transition, not a fault.
                now_playing_network.textContent = 'Ready';
                now_playing_status.textContent = status.network_name || '';
                now_playing_title.textContent = '';
                if (!is_inputting_channel && !is_showing_volume && feedback_timeout === null) {
                    display.textContent = self.idleDisplayText();
                }
            }
            else {
                now_playing_network.textContent = status.status || 'Unknown';
                now_playing_status.textContent = '';
                now_playing_title.textContent = '';
                if (!is_inputting_channel && !is_showing_volume && feedback_timeout === null) {
                    display.textContent = 'ERROR';
                }
            }
        }
        // If in system info mode, don't update the display from player status
    };
    /**
     * Show Volume Display
     */
    self.showVolumeDisplay = function(volume_text) {

        // Clear any existing volume timeout
        if (volume_display_timeout) {
            clearTimeout(volume_display_timeout);
        }

        // Set volume display mode
        is_showing_volume = true;
        display.textContent = volume_text;

        // Clear volume display after 3 seconds
        volume_display_timeout = setTimeout(function () {
            is_showing_volume = false;
            volume_display_timeout = null;
            // Return to normal display (will be updated by next status poll)
            if (!is_inputting_channel) {
                display.textContent = self.idleDisplayText();
            }
        }, 3000);
    };
    /**
     * Toggle Info Mode
     */
    self.toggleInfoMode = function() {
        if (info_mode === 'playing') {
            info_mode = 'system';
            display.textContent = 'SYSTEM INFO';
        }
        else {
            info_mode = 'playing';
            display.textContent = 'NOW PLAYING';
        }

        // Immediately poll for the new mode
        self.pollPlayerStatus();
    };
    /**
     * Update System Info
     */
    self.updateSystemInfo = function(info) {
        // Prioritize: CPU temp, CPU load percent, memory used percent

        // Top line: CPU Temperature
        if (info.temperature_c !== undefined) {
            now_playing_network.textContent =
                'CPU ' + info.temperature_c + '°C (' + info.temperature_f + '°F)';
        }
        else if (info.temperature_f !== undefined) {
            now_playing_network.textContent = 'CPU ' + info.temperature_f + '°F';
        }
        else if (info.temperature === 'unavailable') {
            // WSL/virtualized environment - show system type instead
            const system_type = info.system?.platform || 'Unknown';
            const arch = info.system?.architecture || '';
            now_playing_network.textContent = ('' + system_type + ' ' + arch).trim();
        }
        else {
            now_playing_network.textContent = 'CPU Temp N/A';
        }

        // Second line: CPU Load
        if (info.cpu && info.cpu.load_percent !== undefined) {
            now_playing_status.textContent = 'CPU Load ' + info.cpu.load_percent + '%';
        }
        else if (info.cpu && info.cpu.load_1min !== undefined) {
            now_playing_status.textContent = 'Load ' + info.cpu.load_1min;
        }
        else {
            now_playing_status.textContent = 'CPU Load N/A';
        }

        // Third line: Memory Usage
        if (info.memory && info.memory.used_percent !== undefined) {
            now_playing_title.textContent =
                'Memory ' +
                info.memory.used_percent +
                '% (' +
                info.memory.used_gb +
                '/' +
                info.memory.total_gb +
                'GB)';
        }
        else {
            now_playing_title.textContent = 'Memory N/A';
        }
    };
    /**
     * Poll Player Status
     */
    self.pollPlayerStatus = async function() {
        if (status_pending) return;
        status_pending = true;
        const epoch = status_epoch;
        const mode = info_mode;
        try {
            if (mode === 'playing') {
                const status = await apiGet('api.player.get_player_status');
                if (epoch === status_epoch && mode === info_mode) self.updateNowPlayingFromStatus(status);
            }
            else if (mode === 'system') {
                const info = await apiGet('api.player.get_info');
                if (epoch === status_epoch && mode === info_mode) self.updateSystemInfo(info);
            }
        }
        catch (error) {
            if (epoch !== status_epoch || mode !== info_mode) return;
            console.error('Failed to get status/info:', error);
            if (info_mode === 'playing') {
                now_playing_network.textContent = 'Unknown';
                now_playing_status.textContent = '';
                now_playing_title.textContent = '';
            }
            else {
                now_playing_network.textContent = 'System';
                now_playing_status.textContent = 'Error';
                now_playing_title.textContent = 'Unable to get info';
            }
        }
        finally {
            if (epoch === status_epoch) status_pending = false;
        }
    };
    /**
     * Start Status Polling
     */
    self.startStatusPolling = function() {
        if (status_poll_interval) {
            clearInterval(status_poll_interval);
        }
        status_poll_interval = setInterval(self.pollPlayerStatus, 1000);
        // Get initial status immediately
        self.pollPlayerStatus();
    };
    /**
     * Stop Status Polling
     */
    self.stopStatusPolling = function() {
        status_epoch++;
        status_pending = false;
        if (status_poll_interval) {
            clearInterval(status_poll_interval);
            status_poll_interval = null;
        }
    };
    /**
     * Toggle Pad
     */
    self.togglePad = function() {
        pad_mode = pad_mode === 'number' ? 'nav' : 'number';
        number_pad.hidden = pad_mode !== 'number';
        nav_pad.hidden = pad_mode !== 'nav';
        display.textContent = pad_mode === 'nav' ? 'NAV PAD' : 'NUMBERS';
    };
    /**
     * Send Parental Digit
     */
    self.sendParentalDigit = async function(digit) {
        try {
            await sendControl('parental.digit', {digit:digit});
            // Count it locally so the display reacts at once - the next poll
            // replaces this with the count the player confirms.
            pin_digits_entered += 1;
            display.textContent = self.idleDisplayText();
        }
        catch (error) {
            console.error('Parental digit failed:', error);
            display.textContent = 'ERROR';
        }
    };
    /**
     * Handle Clear
     */
    self.handleClear = async function() {
        if (awaiting_pin) {
            try {
                await sendControl('parental.clear');
                pin_digits_entered = 0;
                display.textContent = self.idleDisplayText();
            }
            catch (error) {
                console.error('Parental clear failed:', error);
                display.textContent = 'ERROR';
            }
            return;
        }

        // Not locked, so drop whatever channel number is half-entered.
        if (channel_input_timeout) {
            clearTimeout(channel_input_timeout);
            channel_input_timeout = null;
        }
        channel_input = '';
        is_inputting_channel = false;
        display.textContent = self.idleDisplayText();
    };
    /**
     * Handle Number Input
     */
    self.handleNumberInput = function(digit) {
        // Set input mode
        is_inputting_channel = true;

        // Clear any existing timeout
        if (channel_input_timeout) {
            clearTimeout(channel_input_timeout);
            channel_input_timeout = null;
        }

        // Add digit to input
        channel_input += digit;

        // Display the accumulated input
        display.textContent = channel_input;

        // If we have 3 digits, send immediately
        if (channel_input.length >= 3) {
            self.sendChannelChange();
        }
        else {
            // Set timeout for 1 second
            channel_input_timeout = setTimeout(self.sendChannelChange, 1000);
        }
    };
    /**
     * Send Channel Change
     */
    self.sendChannelChange = async function() {
        if (channel_input_timeout) {
            clearTimeout(channel_input_timeout);
            channel_input_timeout = null;
        }
        const input = channel_input;
        channel_input = '';
        is_inputting_channel = false;
        if (input) {
            try {
                const channel_number = parseInt(input, 10);
                await sendControl('channel.tune', {channel:channel_number});
                // The status polling will update the display with actual channel info
            }
            catch (error) {
                console.error('Channel change failed:', error);
                self.showFeedback('ERROR');
            }
        }
    };
    let feedback_timeout = null;
    let bindings = null;

    /** Register only page-local behaviors here; device actions come from the shared catalog. */
    self.localActions = {
        'remote.digit': async function({digit}) {
            if (awaiting_pin) await self.sendParentalDigit(digit);
            else self.handleNumberInput(digit);
        },
        'remote.clear': function() { return self.handleClear(); },
        'remote.pad_toggle': function() { self.togglePad(); },
        'remote.info': function() { self.toggleInfoMode(); },
        'remote.exit': function() { window.location.href = urlFor('/'); }
    };

    self.showFeedback = function(label, persistent=false) {
        if (feedback_timeout !== null) clearTimeout(feedback_timeout);
        feedback_timeout = null;
        display.textContent = label;
        if (!persistent) feedback_timeout = setTimeout(function() {
            feedback_timeout = null;
            if (!is_inputting_channel && !is_showing_volume) display.textContent = self.idleDisplayText();
        }, 2000);
    };

    /** Dispatch by action identity rather than button identity, with one error/feedback path. */
    self.handleRemoteCommand = async function(action, arguments_={}) {
        const local = Object.hasOwn(self.localActions, action) ? self.localActions[action] : null;
        if (local) return local(arguments_);
        const result = await sendControl(action, arguments_);
        const label = window.fs42Controls.actions[action].label;
        if (action.startsWith('volume.')) self.showVolumeDisplay(result.volume ?? label);
        else self.showFeedback(label, action === 'player.stop');
        if (action === 'menu.on_demand') {
            if (pad_mode !== 'nav') self.togglePad();
            self.showFeedback(label);
        }
        return result;
    };

    self.onControlError = function(error) {
        console.error('Remote control failed:', error);
        self.showFeedback('ERROR');
    };

    self.cleanUp = function() {
        bindings?.destroy();
        bindings = null;
        self.stopStatusPolling();
        for (const timer of [feedback_timeout, channel_input_timeout, volume_display_timeout]) {
            if (timer !== null) clearTimeout(timer);
        }
        feedback_timeout = channel_input_timeout = volume_display_timeout = null;
        channel_input = '';
        is_inputting_channel = is_showing_volume = false;
    };

    self.setup = async function() {
        self.cleanUp();
        display = document.getElementById('remote-display');
        now_playing_network = document.getElementById('now-playing-network');
        now_playing_status = document.getElementById('now-playing-status');
        now_playing_title = document.getElementById('now-playing-title');
        number_pad = document.getElementById('number-pad');
        nav_pad = document.getElementById('nav-pad');
        bindings = new ControlBindings(document, {onControl:self.handleRemoteCommand, onError:self.onControlError});
        display.textContent = self.idleDisplayText();
        now_playing_network.textContent = 'Loading...';
        now_playing_status.textContent = '';
        now_playing_title.textContent = '';
        self.startStatusPolling();
        window.addEventListener('beforeunload', self.cleanUp);
    };
    return self;
})();
