/*
This Source Code Form is subject to the Mozilla Public License, v. 2.0.
See https://mozilla.org/MPL/2.0/.
*/
window.app = window.app || {};
app.tools = app.tools || {};
app.tools.guide_frame = (function () {
    let self = {};
    /**
     * Set up the guide frame page
     */
    self.setup = function () {
        let stations = [];
        let current_time = new Date();
        let guide_start_time = new Date();
        let guide_end_time = new Date();
        let scroll_interval = null;
        let vertical_scroll_interval = null;
        let auto_scroll_enabled = true; // Will be initialized from localStorage
        let debug_show_filename = false; // Debug: show raw file name instead of normalized title
        const virtual_scroll_position = 0;
        const TIME_SLOT_WIDTH = 120; // pixels per 30-minute slot
        const SCROLL_SPEED = 0.033; // pixels per second (1 pixel per 30 seconds = slow realistic scroll)
        const VERTICAL_SCROLL_SPEED = 0.8; // pixels per scroll step for stations (ultra-smooth and relaxed)

        // Feature Flags
        const ENABLE_BACKGROUND_MUSIC = false; // Set to true to enable background music

        // Background Music Playlist
        const music_playlist = [
            '/static/music/guide-track-1.mp3',
            '/static/music/guide-track-2.mp3',
            '/static/music/guide-track-3.mp3',
            '/static/music/guide-track-4.mp3'
        ];
        let current_track_index = 0;

        // Format date for API (YYYY-MM-DDTHH:MM:SS)
        /**
         * Format Date For API
         */
        function formatDateForAPI(date) {
            const year = date.getFullYear();
            const month = String(date.getMonth() + 1).padStart(2, '0');
            const day = String(date.getDate()).padStart(2, '0');
            const hours = String(date.getHours()).padStart(2, '0');
            const minutes = String(date.getMinutes()).padStart(2, '0');
            const seconds = String(date.getSeconds()).padStart(2, '0');
            return '' + year + '-' + month + '-' + day + 'T' + hours + ':' + minutes + ':' + seconds;
        }
        document.addEventListener('DOMContentLoaded', async function () {
            // Initialize auto-scroll setting from localStorage
            const saved_setting = localStorage.getItem('fs42-autoscroll');
            auto_scroll_enabled = saved_setting !== 'false'; // Default to true if not set

            // Initialize debug (show file name) setting from localStorage
            debug_show_filename = localStorage.getItem('fs42-guide-debug') === 'true';
            const content =
                [
                    '',
                    '        <div class="guide-container">',
                    '            <div class="guide-timeline" id="timeline"></div>',
                    '            <div class="guide-content">',
                    '                <div class="guide-stations" id="stations-column"></div>',
                    '                <div class="guide-grid-container">',
                    '                    <div class="guide-grid" id="guide-grid"></div>',
                    '                </div>',
                    '            </div>',
                    '            <div class="branding-overlay" id="branding-overlay">',
                    '                <div class="branding-content">',
                    '                    <div class="branding-title">FieldStation42</div>',
                    '                    <div class="branding-subtitle">It\'s Up To You</div>',
                    '                </div>',
                    '            </div>',
                    '        </div>',
                    '',
                    '        '
                ].join('\n') +
                (ENABLE_BACKGROUND_MUSIC
                    ? [
                          '',
                          '        <!-- Background Music Player -->',
                          '        <audio id="background-music" preload="auto" loop volume="0.3">',
                          '            <source src="/static/music/guide-track-1.mp3" type="audio/mpeg">',
                          '            <source src="/static/music/guide-track-1.ogg" type="audio/ogg">',
                          '        </audio>',
                          '        '
                      ].join('\n')
                    : '') +
                '\n    ';
            document.body.innerHTML = content;

            // Initialize guide
            await initializeGuide();

            // Initialize background music
            initializeMusic();

            // Start auto-scroll and time updates
            startTimeUpdate();
            startAutoScroll();

            // Enable the debug toggle (press "d" to switch between title and file name)
            initDebugToggle();
        });
        /**
         * Init Debug Toggle
         */
        function initDebugToggle() {
            updateDebugIndicator();
            document.addEventListener('keydown', function (e) {
                // Ignore if the user is typing into a field
                const tag = (e.target.tagName || '').toLowerCase();
                if (tag === 'input' || tag === 'textarea') {
                    return;
                }
                if (e.key === 'd' || e.key === 'D') {
                    toggleDebugFilename();
                }
            });
        }

        // Toggle between normalized titles and raw file names.
        // Exposed on window so the parent page's button can call it too.
        /**
         * Toggle Debug Filename
         */
        function toggleDebugFilename() {
            setDebugFilename(!debug_show_filename);
        }
        window.toggleDebugFilename = toggleDebugFilename;
        /**
         * Set Debug Filename
         */
        function setDebugFilename(enabled) {
            debug_show_filename = !!enabled;
            localStorage.setItem('fs42-guide-debug', debug_show_filename);
            updateDebugIndicator();
            // Re-render the schedule in place so titles/file names update
            // immediately, keeping the current vertical scroll position
            // (the grid has a full-height blank spacer at the top, so we
            // must preserve scrollTop or the view lands on empty space).
            refreshScheduleInPlace();
        }
        window.setDebugFilename = setDebugFilename;

        // Let the parent page read current state (localStorage is shared, but
        // this keeps the source of truth in one place).
        window.isDebugFilename = function () {
            return debug_show_filename;
        };
        /**
         * Update Debug Indicator
         */
        function updateDebugIndicator() {
            let indicator = document.getElementById('debug-indicator');
            if (!debug_show_filename) {
                if (indicator) {
                    indicator.remove();
                }
                return;
            }
            if (!indicator) {
                indicator = document.createElement('div');
                indicator.id = 'debug-indicator';
                indicator.style.cssText =
                    'position:fixed;bottom:8px;right:8px;z-index:2000;' +
                    'padding:4px 10px;border-radius:4px;' +
                    'background:rgba(255,0,0,0.75);color:#fff;' +
                    'font-family:monospace;font-size:12px;pointer-events:none;';
                indicator.textContent = 'DEBUG: file names (press "d")';
                document.body.appendChild(indicator);
            }
        }
        /**
         * Refresh Schedule In Place
         */
        async function refreshScheduleInPlace() {
            const stations_column = document.getElementById('stations-column');
            const guide_grid_container = document.querySelector('.guide-grid-container');
            const saved_top = stations_column ? stations_column.scrollTop : 0;
            await loadScheduleData();

            // Restore the scroll position so we don't land on the top blank spacer
            if (stations_column) {
                stations_column.scrollTop = saved_top;
            }
            if (guide_grid_container) {
                guide_grid_container.scrollTop = saved_top;
            }
        }

        // Return the raw source file name (basename) for a schedule block, if known
        /**
         * Get Block Filename
         */
        function getBlockFilename(block) {
            const path = block.content && (block.content.path || block.content.realpath);
            if (!path) {
                return null;
            }
            return path.split(/[\\/]/).pop();
        }
        /**
         * Initialize Guide
         */
        async function initializeGuide() {
            current_time = new Date();

            // Always start at the current 30-minute boundary
            const now = new Date();
            const minutes = now.getMinutes();
            const current_slot = Math.floor(minutes / 30) * 30;
            guide_start_time = new Date(
                now.getFullYear(),
                now.getMonth(),
                now.getDate(),
                now.getHours(),
                current_slot,
                0,
                0
            );
            guide_end_time = new Date(guide_start_time.getTime() + 2 * 60 * 60 * 1000); // 2 hours total

            // Load all stations
            const all_stations = await window.fs42Common.fetchStationSummary();

            // Filter out hidden stations
            stations = all_stations.filter(function (station) {
                return !station.hidden;
            });

            // Mark stations with/without schedules
            stations.forEach(function (station) {
                station.has_schedule =
                    station.schedule_summary &&
                    station.schedule_summary.start !== 0 &&
                    station.schedule_summary.end !== 0;
            });
            if (stations.length === 0) {
                document.getElementById('guide-grid').innerHTML = '<p>No stations found.</p>';
                return;
            }

            // Create timeline
            createTimeline();

            // Create stations column
            createStationsColumn();

            // Load and display schedule data
            await loadScheduleData();

            // Set initial scroll position to show first station at top
            const stations_column = document.getElementById('stations-column');
            const guide_grid_container = document.querySelector('.guide-grid-container');
            const container_height = window.innerHeight - 40; // Use full height minus timeline

            stations_column.scrollTop = container_height;
            guide_grid_container.scrollTop = container_height;
        }
        /**
         * Create Timeline
         */
        function createTimeline() {
            const timeline = document.getElementById('timeline');
            const total_minutes = (guide_end_time - guide_start_time) / (1000 * 60);
            const total_slots = Math.ceil(total_minutes / 30);

            // Add clock in the left space (above stations column) - fixed width
            let timeline_html = '<div class="timeline-clock" id="current-time-display"></div>';

            // Calculate available width for time slots (full width minus 120px for clock)
            const slot_width = 'calc((100% - 120px) / ' + total_slots + ')';
            for (let i = 0; i <= total_slots; i++) {
                const slot_time = new Date(guide_start_time.getTime() + i * 30 * 60 * 1000);
                const time_str = slot_time.toLocaleTimeString('en-US', {
                    hour: '2-digit',
                    minute: '2-digit',
                    hour12: false
                });
                const slot_left = 'calc(120px + (100% - 120px) * ' + i + ' / ' + total_slots + ')';
                timeline_html +=
                    '<div class="timeline-slot" style="left: ' +
                    slot_left +
                    '; width: ' +
                    slot_width +
                    ';">' +
                    time_str +
                    '</div>';
            }
            timeline.innerHTML = timeline_html;
            timeline.style.width = '100%';

            // Set containers to use full available height
            const guide_grid_container = document.querySelector('.guide-grid-container');
            const guide_grid = document.getElementById('guide-grid');
            const stations_column = document.getElementById('stations-column');
            const stations_height = stations.length * 60;
            const available_height = window.innerHeight - 40; // Subtract timeline height

            // Set containers to full available height for better screen usage
            guide_grid_container.style.height = available_height + 'px';
            stations_column.style.height = available_height + 'px';
            guide_grid.style.height = stations_height + 'px';

            // Hide scrollbars since we're auto-scrolling
            stations_column.style.overflowY = 'hidden';
            guide_grid_container.style.overflowY = 'hidden';
        }
        /**
         * Create Stations Column
         */
        function createStationsColumn() {
            const stations_column = document.getElementById('stations-column');
            const container_height = window.innerHeight - 40; // Use full height minus timeline

            let stations_html = '';

            // Add smooth blank space at the top
            stations_html += '<div style="height: ' + container_height + 'px; background: #0f1b2d;"></div>';

            // Add actual stations
            for (const station of stations) {
                const channel_number = station.channel_number || '?';
                const display_name = station.network_long_name || station.network_name;
                stations_html +=
                    [
                        '',
                        '            <div class="station-row">',
                        '                <div class="station-name">',
                        '                    <div class="channel-number">'
                    ].join('\n') +
                    channel_number +
                    '</div>\n                    <div class="network-name">' +
                    display_name +
                    '</div>\n                </div>\n            </div>\n        ';
            }

            // Add smooth blank space at the bottom
            stations_html += '<div style="height: ' + container_height + 'px; background: #0f1b2d;"></div>';
            stations_column.innerHTML = stations_html;
        }
        /**
         * Load Schedule Data
         */
        async function loadScheduleData() {
            const grid = document.getElementById('guide-grid');
            const total_minutes = (guide_end_time - guide_start_time) / (1000 * 60);
            grid.style.width = '100%';
            grid.innerHTML = '';

            // Add smooth blank space at the top to match the stations column
            const container_height = window.innerHeight - 40; // Use full height minus timeline
            const top_blank_div = document.createElement('div');
            top_blank_div.style.height = container_height + 'px';
            top_blank_div.style.width = '100%';
            top_blank_div.style.background = '#0f1b2d';
            grid.appendChild(top_blank_div);
            for (let station_index = 0; station_index < stations.length; station_index++) {
                const station = stations[station_index];
                const station_row = document.createElement('div');
                station_row.className = 'guide-row';

                // Check if station has schedule
                if (!station.has_schedule) {
                    // No schedule - show single bar with network name
                    const no_schedule_block = document.createElement('div');
                    no_schedule_block.className = 'program-block no-schedule';
                    no_schedule_block.style.left = '0px';
                    no_schedule_block.style.width = '100%';
                    const display_name = station.network_long_name || station.network_name;
                    no_schedule_block.innerHTML = '<span class="program-title">' + display_name + '</span>';
                    station_row.appendChild(no_schedule_block);
                    grid.appendChild(station_row);
                    continue;
                }
                try {
                    // Fetch a wider time range to include shows that started before our guide window
                    // but might still be airing during our guide time
                    const extended_start_time = new Date(guide_start_time.getTime() - 3 * 60 * 60 * 1000); // 3 hours before
                    const schedule_blocks = await window.fs42Common.fetchSchedule(
                        station.network_name,
                        formatDateForAPI(extended_start_time),
                        formatDateForAPI(guide_end_time)
                    );
                    if (schedule_blocks && schedule_blocks.length > 0) {
                        for (const block of schedule_blocks) {
                            const block_element = createProgramBlock(block);
                            if (block_element) {
                                station_row.appendChild(block_element);
                            }
                        }
                    }
                    else {
                        // No programming data
                        const empty_block = document.createElement('div');
                        empty_block.className = 'program-block no-programming';
                        empty_block.style.left = '0px';
                        empty_block.style.width = '100%';
                        empty_block.innerHTML = '<span class="program-title">No Programming Data</span>';
                        station_row.appendChild(empty_block);
                    }
                }
                catch (error) {
                    console.error('Error loading schedule for', station.network_name, error);
                    // Show error block
                    const error_block = document.createElement('div');
                    error_block.className = 'program-block error';
                    error_block.style.left = '0px';
                    error_block.style.width = '100%';
                    error_block.innerHTML = '<span class="program-title">Error loading schedule</span>';
                    station_row.appendChild(error_block);
                }
                grid.appendChild(station_row);
            }

            // Add smooth blank space at the bottom to match the stations column
            const bottom_blank_div = document.createElement('div');
            bottom_blank_div.style.height = container_height + 'px';
            bottom_blank_div.style.width = '100%';
            bottom_blank_div.style.background = '#0f1b2d';
            grid.appendChild(bottom_blank_div);
        }
        /**
         * Create Program Block
         */
        function createProgramBlock(block) {
            const block_start = new Date(block.start_time);
            const block_end = new Date(block.end_time);

            // Check if block overlaps with our guide time range
            if (block_end < guide_start_time || block_start > guide_end_time) {
                return null;
            }

            // Calculate position and width
            const guide_start_ms = guide_start_time.getTime();
            const guide_end_ms = guide_end_time.getTime();
            const block_start_ms = block_start.getTime();
            const block_end_ms = block_end.getTime();

            // Clamp the block to the visible guide time range
            const visible_start_ms = Math.max(guide_start_ms, block_start_ms);
            const visible_end_ms = Math.min(guide_end_ms, block_end_ms);
            const start_offset = (visible_start_ms - guide_start_ms) / (1000 * 60); // minutes from guide start
            const end_offset = (visible_end_ms - guide_start_ms) / (1000 * 60); // minutes from guide start
            const duration = end_offset - start_offset; // duration in minutes within the guide range

            // Calculate as percentages of the available program area (after 120px clock space)
            const total_minutes = (guide_end_ms - guide_start_ms) / (1000 * 60);
            const left_percent = (start_offset / total_minutes) * 100;
            const width_percent = (duration / total_minutes) * 100;
            const left = 'calc(' + left_percent + '% + 1.5px)';
            const width = 'calc(' + width_percent + '% - 3px)';
            const program_div = document.createElement('div');
            program_div.className = 'program-block';
            program_div.style.left = left;
            program_div.style.width = width;

            // Add current program class if it's currently airing
            if (block_start <= current_time && block_end > current_time) {
                program_div.classList.add('current-program');
            }
            let title = block.title || 'Untitled';
            if (debug_show_filename) {
                title = getBlockFilename(block) || title;
            }
            const start_time = block_start.toLocaleTimeString('en-US', {
                hour: '2-digit',
                minute: '2-digit',
                hour12: false
            });
            program_div.innerHTML =
                '\n        <span class="program-title">' +
                title +
                '</span>\n        <span class="program-time">' +
                start_time +
                '</span>\n    ';
            return program_div;
        }
        /**
         * Update Timeline Marker
         */
        function updateTimelineMarker() {
            // Remove any existing marker
            const existing_marker = document.querySelector('.current-time-marker');
            if (existing_marker) {
                existing_marker.remove();
            }
            const minutes_from_start = (current_time - guide_start_time) / (1000 * 60);
            const total_minutes = (guide_end_time - guide_start_time) / (1000 * 60);
            const time_percent = (minutes_from_start / total_minutes) * 100;

            // Only show marker if current time is within the guide window
            if (minutes_from_start >= 0 && minutes_from_start <= total_minutes) {
                const timeline = document.getElementById('timeline');
                const marker = document.createElement('div');
                marker.className = 'current-time-marker';
                marker.style.position = 'absolute';
                marker.style.left = 'calc(120px + (100% - 120px) * ' + time_percent + ' / 100)';
                marker.style.top = '32px';
                marker.style.width = '0';
                marker.style.height = '0';
                marker.style.borderLeft = '6px solid transparent';
                marker.style.borderRight = '6px solid transparent';
                marker.style.borderTop = '8px solid #ff0000';
                marker.style.transform = 'translateX(-6px)'; // Center the triangle
                marker.style.zIndex = '1000';
                marker.style.filter = 'drop-shadow(0 0 4px #ff0000)';
                timeline.appendChild(marker);
            }
        }
        /**
         * Start Time Update
         */
        function startTimeUpdate() {
            setInterval(function () {
                current_time = new Date();
                const time_display = document.getElementById('current-time-display');
                if (!time_display) {
                    return;
                }
                time_display.textContent = current_time.toLocaleTimeString('en-US', {
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit',
                    hour12: false
                });
                updateTimelineMarker();
            }, 1000);
        }
        /**
         * Start Auto Scroll
         */
        function startAutoScroll() {
            if (scroll_interval) {
                clearInterval(scroll_interval);
            }

            // Check every minute if we need to advance the guide
            scroll_interval = setInterval(function () {
                if (auto_scroll_enabled) {
                    checkTimeAdvance();
                }
            }, 60000); // Check every minute

            // Start vertical scrolling of stations
            startVerticalScroll();
        }
        /**
         * Start Vertical Scroll
         */
        function startVerticalScroll() {
            if (vertical_scroll_interval) {
                clearInterval(vertical_scroll_interval);
            }
            vertical_scroll_interval = setInterval(function () {
                if (auto_scroll_enabled) {
                    const stations_column = document.getElementById('stations-column');
                    const guide_grid_container = document.querySelector('.guide-grid-container');
                    if (stations_column && guide_grid_container) {
                        const max_scroll = stations_column.scrollHeight - stations_column.clientHeight;
                        const container_height = window.innerHeight - 40;
                        const stations_height = stations.length * 60;

                        // Only scroll if there are enough stations to warrant scrolling
                        // (stations must fill more than the visible container height)
                        if (max_scroll > 0 && stations_height > container_height) {
                            // Get current scroll position
                            const current_scroll = stations_column.scrollTop;
                            let next_scroll = current_scroll + VERTICAL_SCROLL_SPEED;

                            // Check if we're in the blank space area and should show branding
                            const stationsHeight = stations.length * 60;
                            const blank_space_height = window.innerHeight - 40;

                            // Simple range check: show branding from when last station is nearly gone
                            // until we've scrolled enough after reset to see stations from bottom
                            const show_start = blank_space_height + stationsHeight - 100; // Show when near end
                            const hide_after_reset = 200; // Hide when we've scrolled 200px after reset (stations should be visible)

                            const should_show_branding =
                                current_scroll >= show_start || current_scroll <= hide_after_reset;

                            // Only show branding if viewport is tall enough (skip for small iframes)
                            const viewport_height = window.innerHeight;
                            const should_show_branding_with_height_check =
                                should_show_branding && viewport_height >= 400;

                            // Show/hide branding overlay
                            if (should_show_branding_with_height_check) {
                                showBrandingOverlay();
                            }
                            else {
                                hideBrandingOverlay();
                            }

                            // Reset to top when we reach the bottom (now includes blank space)
                            if (next_scroll >= max_scroll) {
                                next_scroll = 0;
                            }

                            // Apply scroll to both containers
                            stations_column.scrollTop = next_scroll;
                            guide_grid_container.scrollTop = next_scroll;
                        }
                    }
                }
            }, 50); // Update every 50ms (20 times per second) for ultra-smooth scrolling
        }
        /**
         * Check Time Advance
         */
        function checkTimeAdvance() {
            const now = new Date();
            const current_minutes = now.getMinutes();
            const current_slot = Math.floor(current_minutes / 30) * 30;
            const expected_start_time = new Date(
                now.getFullYear(),
                now.getMonth(),
                now.getDate(),
                now.getHours(),
                current_slot,
                0,
                0
            );

            // If we've crossed into a new 30-minute boundary, advance the guide
            if (expected_start_time.getTime() !== guide_start_time.getTime()) {
                console.log('Advancing guide to new 30-minute slot');
                guide_start_time = expected_start_time;
                guide_end_time = new Date(guide_start_time.getTime() + 2 * 60 * 60 * 1000);

                // Reload the guide data
                reloadGuideData();
            }
        }
        /**
         * Reload Guide Data
         */
        async function reloadGuideData() {
            // Update timeline
            createTimeline();

            // Reload schedule data
            await loadScheduleData();

            // Reset scroll position to start
            const container = document.querySelector('.guide-grid-container');
            container.scrollLeft = 0;
        }
        /**
         * Show Branding Overlay
         */
        function showBrandingOverlay() {
            const overlay = document.getElementById('branding-overlay');
            if (overlay && !overlay.classList.contains('visible')) {
                overlay.classList.add('visible');

                // Start cycling messages every 7 seconds
                if (!branding_cycle_interval) {
                    // Set initial message immediately without transition
                    const title_element = document.querySelector('.branding-title');
                    const subtitle_element = document.querySelector('.branding-subtitle');
                    if (title_element && subtitle_element) {
                        const initial_message = branding_messages[branding_message_index];
                        title_element.textContent = initial_message.title;
                        subtitle_element.textContent = initial_message.subtitle;
                        branding_message_index = (branding_message_index + 1) % branding_messages.length;
                    }

                    // Start cycling for subsequent messages
                    branding_cycle_interval = setInterval(cycleBrandingMessage, 7000);
                }
            }
        }
        /**
         * Hide Branding Overlay
         */
        function hideBrandingOverlay() {
            const overlay = document.getElementById('branding-overlay');
            if (overlay && overlay.classList.contains('visible')) {
                overlay.classList.remove('visible');

                // Stop cycling messages
                if (branding_cycle_interval) {
                    clearInterval(branding_cycle_interval);
                    branding_cycle_interval = null;
                    branding_message_index = 0; // Reset to first message for next time
                }
            }
        }

        // Branding message cycling
        let branding_message_index = 0;
        const branding_messages = [
            {
                title: 'FieldStation42',
                subtitle: "It's Up To You"
            },
            {
                title: 'Cable Television',
                subtitle: 'The Way You Like It'
            }
        ];
        let branding_cycle_interval = null;
        /**
         * Cycle Branding Message
         */
        function cycleBrandingMessage() {
            const title_element = document.querySelector('.branding-title');
            const subtitle_element = document.querySelector('.branding-subtitle');
            const content_element = document.querySelector('.branding-content');
            if (title_element && subtitle_element && content_element) {
                // Fade out
                content_element.style.opacity = '0';
                content_element.style.transform = 'translateY(20px) scale(0.95)';
                setTimeout(function () {
                    // Change text while faded out
                    const current_message = branding_messages[branding_message_index];
                    title_element.textContent = current_message.title;
                    subtitle_element.textContent = current_message.subtitle;
                    branding_message_index = (branding_message_index + 1) % branding_messages.length;

                    // Fade back in
                    content_element.style.opacity = '1';
                    content_element.style.transform = 'translateY(0) scale(1)';
                }, 500); // Half second fade out duration
            }
        }

        // Music Player Functions
        /**
         * Initialize Music
         */
        function initializeMusic() {
            if (!ENABLE_BACKGROUND_MUSIC) {
                console.log('Background music is disabled by feature flag');
                return;
            }
            const audio = document.getElementById('background-music');
            if (!audio) {
                return;
            }

            // Set initial volume
            audio.volume = 0.3;

            // Handle track ended - play next in playlist
            audio.addEventListener('ended', function () {
                playNextTrack();
            });

            // Handle errors - try next track
            audio.addEventListener('error', function () {
                console.log('Error loading track, trying next...');
                playNextTrack();
            });

            // Auto-start music (may require user interaction first)
            tryPlayMusic();
        }
        /**
         * Try Play Music
         */
        function tryPlayMusic() {
            if (!ENABLE_BACKGROUND_MUSIC) {
                return;
            }
            const audio = document.getElementById('background-music');
            if (!audio) {
                return;
            }
            audio.play().catch(function (error) {
                console.log('Auto-play blocked, music will start on user interaction');
                // Add click listener to start music on first user interaction
                document.addEventListener(
                    'click',
                    /**
                     * Start Music On Click
                     */
                    function start_music_on_click() {
                        audio.play();
                        document.removeEventListener('click', start_music_on_click);
                    },
                    {
                        once: true
                    }
                );
            });
        }
        /**
         * Play Next Track
         */
        function playNextTrack() {
            if (!ENABLE_BACKGROUND_MUSIC) {
                return;
            }
            const audio = document.getElementById('background-music');
            if (!audio) {
                return;
            }
            current_track_index = (current_track_index + 1) % music_playlist.length;
            const next_track = music_playlist[current_track_index];

            // Update audio source
            audio.src = next_track;
            audio.load();
            audio.play().catch(function (error) {
                console.log('Error playing next track:', error);
            });
        }
        /**
         * Toggle Music
         */
        function toggleMusic() {
            if (!ENABLE_BACKGROUND_MUSIC) {
                return;
            }
            const audio = document.getElementById('background-music');
            if (!audio) {
                return;
            }
            if (audio.paused) {
                audio.play();
            }
            else {
                audio.pause();
            }
        }
        self.formatDateForAPI = formatDateForAPI;
        self.initDebugToggle = initDebugToggle;
        self.toggleDebugFilename = toggleDebugFilename;
        self.setDebugFilename = setDebugFilename;
        self.updateDebugIndicator = updateDebugIndicator;
        self.refreshScheduleInPlace = refreshScheduleInPlace;
        self.getBlockFilename = getBlockFilename;
        self.initializeGuide = initializeGuide;
        self.createTimeline = createTimeline;
        self.createStationsColumn = createStationsColumn;
        self.loadScheduleData = loadScheduleData;
        self.createProgramBlock = createProgramBlock;
        self.updateTimelineMarker = updateTimelineMarker;
        self.startTimeUpdate = startTimeUpdate;
        self.startAutoScroll = startAutoScroll;
        self.startVerticalScroll = startVerticalScroll;
        self.checkTimeAdvance = checkTimeAdvance;
        self.reloadGuideData = reloadGuideData;
        self.showBrandingOverlay = showBrandingOverlay;
        self.hideBrandingOverlay = hideBrandingOverlay;
        self.cycleBrandingMessage = cycleBrandingMessage;
        self.initializeMusic = initializeMusic;
        self.tryPlayMusic = tryPlayMusic;
        self.playNextTrack = playNextTrack;
        self.toggleMusic = toggleMusic;
    };
    return self;
})();
