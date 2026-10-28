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
    const volume = 50;
    const muted = false;
    let status_poll_interval = null;
    let channel_input = '';
    let channel_input_timeout = null;
    let is_inputting_channel = false;
    let volume_display_timeout = null;
    let is_showing_volume = false;
    const is_showing_info = false;
    let info_mode = 'playing'; // 'playing' or 'system'
    let pad_mode = 'number'; // 'number' or 'nav'
    let awaiting_pin = false;
    let guide_visible = false;
    let pin_digits_entered = 0;
    let number_pad = null;
    let nav_pad = null;
    const program_data = {
        '001': {
            title: 'Morning News',
            info: 'Local and world news updates'
        },
        '002': {
            title: 'Classic Movies',
            info: 'The Maltese Falcon (1941)'
        },
        '003': {
            title: 'Nature Documentary',
            info: 'Wildlife of the Amazon'
        },
        '004': {
            title: 'Cooking Show',
            info: 'Italian Pasta Masterclass'
        },
        '005': {
            title: 'Sitcom Reruns',
            info: 'Comedy Hour Marathon'
        }
    };

    /**
     * Update Now Playing
     */
    self.updateNowPlaying = function(channel) {
        const program = program_data[channel];
        if (program) {
            now_playing_title.textContent = program.title;
            nowPlayingInfo.textContent = program.info;
        }
        else {
            now_playing_title.textContent = 'Channel ' + channel;
            nowPlayingInfo.textContent = 'Program information unavailable';
        }
    };
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
        guide_visible = !!status.guide_visible;
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
                    if (!is_inputting_channel && !is_showing_volume) {
                        display.textContent = self.idleDisplayText();
                    }
                }
            }
            else if (status.status === 'stopped') {
                now_playing_network.textContent = 'Stopped';
                now_playing_status.textContent = '';
                now_playing_title.textContent = '';
                if (!is_inputting_channel && !is_showing_volume) {
                    display.textContent = 'STOPPED';
                }
            }
            else if (status.status === 'idle') {
                // The player hands back from parental controls as 'idle' and
                // starts playing a moment later - a transition, not a fault.
                now_playing_network.textContent = 'Ready';
                now_playing_status.textContent = status.network_name || '';
                now_playing_title.textContent = '';
                if (!is_inputting_channel && !is_showing_volume) {
                    display.textContent = self.idleDisplayText();
                }
            }
            else {
                now_playing_network.textContent = status.status || 'Unknown';
                now_playing_status.textContent = '';
                now_playing_title.textContent = '';
                if (!is_inputting_channel && !is_showing_volume) {
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
        console.log('showVolumeDisplay called with:', volume_text);

        // Clear any existing volume timeout
        if (volume_display_timeout) {
            clearTimeout(volume_display_timeout);
        }

        // Set volume display mode
        is_showing_volume = true;
        display.textContent = volume_text;
        console.log('Display set to:', display.textContent);

        // Clear volume display after 3 seconds
        volume_display_timeout = setTimeout(function () {
            console.log('Volume display timeout - returning to normal');
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
            console.log('Switched to system info mode');
        }
        else {
            info_mode = 'playing';
            display.textContent = 'NOW PLAYING';
            console.log('Switched to now playing mode');
        }

        // Immediately poll for the new mode
        self.pollPlayerStatus();
    };
    /**
     * Update System Info
     */
    self.updateSystemInfo = function(info) {
        // Prioritize: CPU temp, CPU load percent, memory used percent
        console.log('System info received:', info);

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
        try {
            if (info_mode === 'playing') {
                const status = await apiGet('api.player.get_player_status');
                console.log('Player status response:', status);
                self.updateNowPlayingFromStatus(status);
            }
            else if (info_mode === 'system') {
                const info = await apiGet('api.player.get_info');
                console.log('System info response:', info);
                self.updateSystemInfo(info);
            }
        }
        catch (error) {
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
     * Send Ppv Key
     */
    self.sendPpvKey = async function(key_name, label) {
        const channel_number = parseInt(current_channel, 10);
        try {
            await apiPost('ppv/' + channel_number + '/key/' + key_name);
            display.textContent = label;
            console.log('PPV key ' + key_name + ' sent to channel ' + channel_number);
        }
        catch (error) {
            console.error('PPV key ' + key_name + ' failed:', error);
            display.textContent = 'ERROR';
        }
    };
    /**
     * Send Parental Digit
     */
    self.sendParentalDigit = async function(digit) {
        try {
            await apiPost('player/parental/digit/' + digit);
            // Count it locally so the display reacts at once - the next poll
            // replaces this with the count the player confirms.
            pin_digits_entered += 1;
            display.textContent = self.idleDisplayText();
            console.log('Parental PIN digit sent');
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
                await apiPost('api.player.parental_clear');
                pin_digits_entered = 0;
                display.textContent = self.idleDisplayText();
                console.log('Parental PIN cleared');
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
        if (channel_input) {
            try {
                const channel_number = parseInt(channel_input);
                console.log('Sending channel change to ' + channel_number);
                await apiGet('player/channels/' + channel_number);
                console.log('Changed to channel ' + channel_number);
                // The status polling will update the display with actual channel info
            }
            catch (error) {
                console.error('Channel change failed:', error);
                display.textContent = 'ERROR';
                setTimeout(function () {
                    is_inputting_channel = false;
                    display.textContent = self.idleDisplayText();
                }, 2000);
                return;
            }
        }

        // Clear the input and exit input mode
        channel_input = '';
        is_inputting_channel = false;
    };
    /**
     * Handle Remote Command
     */
    self.handleRemoteCommand = async function(key) {
        switch (key) {
            case 'power':
                try {
                    await apiGet('api.player.player_stop');
                    display.textContent = 'STOPPING';
                    console.log('Player stop command sent');
                }
                catch (error) {
                    console.error('Power/stop command failed:', error);
                    display.textContent = 'ERROR';
                }
                break;
            case '0':
            case '1':
            case '2':
            case '3':
            case '4':
            case '5':
            case '6':
            case '7':
            case '8':
            case '9':
                if (awaiting_pin) {
                    await self.sendParentalDigit(key);
                }
                else {
                    self.handleNumberInput(key);
                }
                break;
            case 'clear':
                await self.handleClear();
                break;
            case 'pad_toggle':
                self.togglePad();
                break;
            case 'nav_up':
                await self.sendPpvKey(guide_visible ? 'ArrowUp' : 'PageUp', 'UP');
                break;
            case 'nav_down':
                await self.sendPpvKey(guide_visible ? 'ArrowDown' : 'PageDown', 'DOWN');
                break;
            case 'nav_left':
                await self.sendPpvKey('ArrowLeft', 'LEFT');
                break;
            case 'nav_right':
                await self.sendPpvKey('ArrowRight', 'RIGHT');
                break;
            case 'nav_enter':
                await self.sendPpvKey('Enter', 'SELECT');
                break;
            case 'back':
                await self.sendPpvKey('Escape', 'BACK');
                break;
            case 'ch_up':
                display.textContent = 'CHANNEL UP';
                try {
                    await apiGet('player/channels/up');
                    console.log('Channel up command sent');
                    // The status polling will update the display with actual channel
                }
                catch (error) {
                    console.error('Channel up failed:', error);
                    display.textContent = 'ERROR';
                    // Return to previous display after 2 seconds
                    setTimeout(function () {
                        display.textContent = self.idleDisplayText();
                    }, 2000);
                }
                break;
            case 'ch_down':
                display.textContent = 'CHANNEL DOWN';
                try {
                    await apiGet('player/channels/down');
                    console.log('Channel down command sent');
                    // The status polling will update the display with actual channel
                }
                catch (error) {
                    console.error('Channel down failed:', error);
                    display.textContent = 'ERROR';
                    // Return to previous display after 2 seconds
                    setTimeout(function () {
                        display.textContent = self.idleDisplayText();
                    }, 2000);
                }
                break;
            case 'vol_up':
                try {
                    const response = await apiGet('api.player.volume_up');
                    self.showVolumeDisplay(response.volume || 'VOL +');
                    console.log('Volume up command sent:', response);
                }
                catch (error) {
                    console.error('Volume up failed:', error);
                    self.showVolumeDisplay('ERROR');
                }
                break;
            case 'vol_down':
                try {
                    const response = await apiGet('api.player.volume_down');
                    self.showVolumeDisplay(response.volume || 'VOL -');
                    console.log('Volume down command sent:', response);
                }
                catch (error) {
                    console.error('Volume down failed:', error);
                    self.showVolumeDisplay('ERROR');
                }
                break;
            case 'mute':
                try {
                    const response = await apiGet('api.player.volume_mute');
                    self.showVolumeDisplay('MUTE');
                    console.log('Mute toggle command sent:', response);
                }
                catch (error) {
                    console.error('Mute failed:', error);
                    self.showVolumeDisplay('ERROR');
                }
                break;
            case 'guide':
                try {
                    await apiPost('api.player.show_guide');
                    display.textContent = 'GUIDE';
                    console.log('Guide command sent');
                }
                catch (error) {
                    console.error('Guide command failed:', error);
                    display.textContent = 'ERROR';
                }
                break;
            case 'on_demand':
                try {
                    await apiPost('api.on_demand.open_menu');
                    guide_visible = true;
                    if (pad_mode !== 'nav') {
                        self.togglePad();
                    }
                    display.textContent = 'ON DEMAND';
                }
                catch (error) {
                    console.error('On Demand command failed:', error);
                    display.textContent = 'ERROR';
                }
                break;
            case 'exit':
                display.textContent = 'EXIT';
                window.location.href = urlFor('/');
                break;
            case 'info':
                self.toggleInfoMode();
                break;
            case 'subtitles':
                try {
                    // Queue a non-interrupting MPV command; station_player.py
                    // cycles the selected subtitle track and displays its label.
                    await apiPost('api.player.mpv_cycle_subtitles');
                    display.textContent = 'SUBTITLES';
                    console.log('Cycle subtitles command sent');
                }
                catch (error) {
                    console.error('Cycle subtitles failed:', error);
                    display.textContent = 'ERROR';
                }
                break;
            case 'audio':
                try {
                    // Same path as subtitles, but cycling the active audio track.
                    await apiPost('api.player.mpv_cycle_audio');
                    display.textContent = 'AUDIO';
                    console.log('Cycle audio command sent');
                }
                catch (error) {
                    console.error('Cycle audio failed:', error);
                    display.textContent = 'ERROR';
                }
                break;
            default:
                display.textContent = key.toUpperCase();
        }

        // Reset display after 2 seconds for non-persistent states
        if (!['power', 'mute'].includes(key)) {
            setTimeout(function () {
                if (display.textContent !== 'OFF') {
                    display.textContent = muted ? 'MUTED' : self.idleDisplayText();
                }
            }, 2000);
        }
    };

    /** Bind page controls and load the initial data. */
    const lastTouchActivation = new WeakMap();

    /** Dispatch a remote press and briefly show button feedback. */
    self.activateButton = function(button) {
        self.handleRemoteCommand(button.getAttribute('data-key'));
        button.style.transform = 'translateY(2px)';
        setTimeout(function() { button.style.transform = ''; }, 100);
    };

    /** Keep appliance controls from triggering browser zoom gestures. */
    self.preventGesture = function(event) {
        event.preventDefault();
    };

    /** Dispatch a touch press and remember it to suppress synthetic clicks. */
    self.onTouchEnd = function(event) {
        event.preventDefault();
        lastTouchActivation.set(event.currentTarget, Date.now());
        self.activateButton(event.currentTarget);
    };

    /** Handle mouse presses while ignoring a click synthesized from a touch. */
    self.onButtonClick = function(event) {
        const touched = lastTouchActivation.get(event.currentTarget);
        if (touched !== undefined && Date.now() - touched < 500) return;
        self.activateButton(event.currentTarget);
    };

    self.setup = async function() {
        display = document.getElementById('remote-display');
        now_playing_network = document.getElementById('now-playing-network');
        now_playing_status = document.getElementById('now-playing-status');
        now_playing_title = document.getElementById('now-playing-title');
        number_pad = document.getElementById('number-pad');
        nav_pad = document.getElementById('nav-pad');
        // Basic remote control functionality
        // Mirrors the player status: while a station is locked, digits enter the
        // PIN instead of changing channel (same rule as fs42/tools/remote_control/remote_control.py).

        // Sample program data (could be fetched from API later)

        // What the display falls back to whenever nothing transient is showing.

        for (const button of document.querySelectorAll('.remote-btn')) {
            button.addEventListener('touchstart', self.preventGesture, {passive: false});
            button.addEventListener('touchend', self.onTouchEnd, {passive: false});
            button.addEventListener('click', self.onButtonClick);
            button.addEventListener('dblclick', self.preventGesture);
        }
        document.addEventListener('gesturestart', self.preventGesture, {passive: false});
        document.addEventListener('gesturechange', self.preventGesture, {passive: false});

        // Initialize display and start polling
        display.textContent = self.idleDisplayText();
        // Don't show sample data, let the polling populate it
        now_playing_network.textContent = 'Loading...';
        now_playing_status.textContent = '';
        now_playing_title.textContent = '';
        self.startStatusPolling();

        // Clean up polling when page is unloaded
        window.addEventListener('beforeunload', self.stopStatusPolling);
    };
    return self;
})();
