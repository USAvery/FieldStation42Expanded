/*
This Source Code Form is subject to the Mozilla Public License, v. 2.0.
See https://mozilla.org/MPL/2.0/.
*/
window.app = window.app || {};
app.tools = app.tools || {};
app.tools.schedule = (function () {
    let self = {};
    /**
     * Set up the schedule page
     */
    self.setup = function () {
        // Declare variables in global scope
        let stations = [];
        let selected_station = null;
        let schedule_extents = {
            start: null,
            end: null
        };
        let add_time_poll_interval = null;
        const add_time_type = null;

        // Initialize page layout
        document.addEventListener('DOMContentLoaded', async function () {
            window.fs42Common.initTheme();
            const log_display = window.fs42Common.createLogDisplay();
            const content =
                [
                    '',
                    '        <div id="search-section" class="pure-u-1" style="margin-bottom: 1.5em; padding-bottom: 1.5em; border-bottom: 2px solid #e0e0e0;">',
                    '            <h3 style="margin-top: 0; color: #ff00cc;">Search</h3>',
                    '            <div class="pure-form" style="display: flex; align-items: center; gap: 0.5em;">',
                    '                <input type="text" id="search-input" placeholder="Search All Schedules..." class="pure-input" style="flex: 1; max-width: 300px;">',
                    '                <button id="search-btn" class="pure-button pure-button-primary">Search</button>',
                    '                <button id="clear-search-btn" class="pure-button">Clear</button>',
                    '            </div>',
                    '            <div id="search-results" style="margin-top: 1em; display: none;">',
                    '                <h3>Search Results</h3>',
                    '                <div id="search-results-content"></div>',
                    '            </div>',
                    '        </div>',
                    '        <div style="margin-bottom: 1em;">',
                    '            <h3 style="margin-top: 0; margin-bottom: 0.5em; color: #ff00cc;">Schedule Operations</h3>',
                    '            <div class="station-select-container">',
                    '                <label for="station-select">Select Station:</label>',
                    '                <select id="station-select" class="pure-input-1"></select>',
                    '                <label for="time-amount-select" style="margin-left: 1em;">Time to Add:</label>',
                    '                <select id="time-amount-select" class="pure-input-1" style="max-width: 150px;">',
                    '                    <option value="month">Month</option>',
                    '                    <option value="week">Week</option>',
                    '                    <option value="day">Day</option>',
                    '                </select>',
                    '                <button id="build-schedule-btn" class="pure-button primary" style="margin-left: 1em;">Add Time</button>',
                    '                <button id="reset-schedules-btn" class="pure-button danger" style="margin-left: 1em;">Reset Schedule</button>',
                    '            </div>',
                    '        </div>',
                    '        <div id="station-summary" class="pure-u-1">',
                    '            <h2 id="station-summary-header" style="display:none;">Station Summary</h2>',
                    '            <div id="station-summary-table"></div>',
                    '        </div>',
                    '        '
                ].join('\n') +
                log_display
                    .replace('log-frame', 'add-time-log-frame')
                    .replace('log-header-text', 'add-time-log-header')
                    .replace('log-dismiss', 'add-time-log-dismiss')
                    .replace('log-content', 'add-time-log') +
                [
                    '',
                    '        <div id="schedule-controls" class="pure-u-1" style="display:none;">',
                    '            <h2 id="schedule-query-header" style="display:none;">Schedule Query</h2>',
                    '            <label for="start-date" id="start-date-label" style="display:none;">Start:</label>',
                    '            <input type="datetime-local" id="start-date" style="margin-right:1em; display:none;">',
                    '            <label for="end-date" id="end-date-label" style="display:none;">End:</label>',
                    '            <input type="datetime-local" id="end-date" style="margin-right:1em; display:none;">',
                    '            <button id="get-schedule" class="pure-button pure-button-primary" style="display:none;">Get Schedule</button>',
                    '        </div>',
                    '        <div id="schedule-table-frame" class="pure-u-1">',
                    '            <h2 id="schedule-blocks-header" style="display:none;">Schedule Blocks</h2>',
                    '            <div id="schedule-table"></div>',
                    '        </div>',
                    '    '
                ].join('\n');
            document.body.innerHTML = await window.fs42Common.createPageLayout('Schedule Manager', content);

            // Initialize functionality after DOM is created
            initializeSchedulePage();

            // Set up search functionality
            setupSearchHandlers();
        });
        /**
         * Initialize Schedule Page
         */
        function initializeSchedulePage() {
            /**
             * Load Stations And Summary
             */
            async function loadStationsAndSummary() {
                stations = await window.fs42Common.fetchStationSummary();
                const select = document.getElementById('station-select');
                select.innerHTML = '';

                // Filter stations that have schedules
                const stations_with_schedules = stations.filter(function (station) {
                    return station._has_schedule;
                });
                const all_opt = document.createElement('option');
                all_opt.value = 'all';
                all_opt.textContent = 'All Channels (' + stations_with_schedules.length + ')';
                select.appendChild(all_opt);
                stations_with_schedules.forEach(function (station) {
                    const opt = document.createElement('option');
                    opt.value = station.network_name;
                    opt.textContent = station.network_name;
                    select.appendChild(opt);
                });
                selected_station = 'all';
                select.value = 'all';
                document.getElementById('station-summary-table').innerHTML = '';
                document.getElementById('station-summary-header').style.display = 'none';
                document.getElementById('schedule-controls').style.display = 'none';
                document.getElementById('schedule-query-header').style.display = 'none';
                document.getElementById('start-date-label').style.display = 'none';
                document.getElementById('start-date').style.display = 'none';
                document.getElementById('end-date-label').style.display = 'none';
                document.getElementById('end-date').style.display = 'none';
                document.getElementById('get-schedule').style.display = 'none';
                document.getElementById('schedule-blocks-header').style.display = 'none';
                document.getElementById('schedule-table').innerHTML = '';
                document.getElementById('add-time-log').textContent = '';
            }
            /**
             * Update Station Summary
             */
            function updateStationSummary(network_name) {
                if (!network_name || network_name === 'all') {
                    document.getElementById('station-summary-table').innerHTML = '';
                    document.getElementById('station-summary-header').style.display = 'none';
                    document.getElementById('schedule-controls').style.display = 'none';
                    document.getElementById('schedule-query-header').style.display = 'none';
                    document.getElementById('start-date-label').style.display = 'none';
                    document.getElementById('start-date').style.display = 'none';
                    document.getElementById('end-date-label').style.display = 'none';
                    document.getElementById('end-date').style.display = 'none';
                    document.getElementById('get-schedule').style.display = 'none';
                    document.getElementById('schedule-blocks-header').style.display = 'none';
                    document.getElementById('schedule-table').innerHTML = '';
                    return;
                }
                const station = stations.find(function (s) {
                    return s.network_name === network_name;
                });
                if (station) {
                    document.getElementById('station-summary-table').innerHTML =
                        window.fs42Common.renderSummaryTable([station]);
                    document.getElementById('station-summary-header').style.display = '';
                    document.getElementById('schedule-controls').style.display = '';
                    document.getElementById('schedule-query-header').style.display = '';
                    document.getElementById('start-date-label').style.display = '';
                    document.getElementById('start-date').style.display = '';
                    document.getElementById('end-date-label').style.display = '';
                    document.getElementById('end-date').style.display = '';
                    document.getElementById('get-schedule').style.display = '';
                }
                else {
                    document.getElementById('station-summary-table').innerHTML = '<p>No summary found.</p>';
                    document.getElementById('station-summary-header').style.display = 'none';
                    document.getElementById('schedule-controls').style.display = 'none';
                    document.getElementById('schedule-query-header').style.display = 'none';
                    document.getElementById('start-date-label').style.display = 'none';
                    document.getElementById('start-date').style.display = 'none';
                    document.getElementById('end-date-label').style.display = 'none';
                    document.getElementById('end-date').style.display = 'none';
                    document.getElementById('get-schedule').style.display = 'none';
                }
            }
            /**
             * Poll Add Time Status
             */
            function pollAddTimeStatus(task_id, after_done_callback) {
                if (add_time_poll_interval) {
                    clearInterval(add_time_poll_interval);
                }
                const log_elem = document.getElementById('add-time-log');
                const header = document.getElementById('add-time-log-header');
                const frame = document.getElementById('add-time-log-frame');
                const dismiss_btn = document.getElementById('add-time-log-dismiss');
                log_elem.textContent = 'Polling add time status...';
                header.style.display = '';
                frame.style.display = '';
                dismiss_btn.style.display = '';
                add_time_poll_interval = setInterval(async function () {
                    try {
                        const resp = await fetch('/build/schedule/add_time/status/' + task_id);
                        const data = await resp.json();
                        if (data.error) {
                            log_elem.textContent = data.error;
                            header.style.display = '';
                            frame.style.display = '';
                            dismiss_btn.style.display = '';
                            clearInterval(add_time_poll_interval);
                            return;
                        }
                        log_elem.textContent = data.log || '';
                        if (data.log && data.log.length > 0) {
                            header.style.display = '';
                            frame.style.display = '';
                            dismiss_btn.style.display = '';
                        }
                        else {
                            header.style.display = 'none';
                            frame.style.display = 'none';
                            dismiss_btn.style.display = 'none';
                        }
                        if (data.status === 'done' || data.status === 'error') {
                            clearInterval(add_time_poll_interval);
                            if (typeof after_done_callback === 'function') {
                                after_done_callback();
                            }
                        }
                    }
                    catch (e) {
                        log_elem.textContent = 'Error polling status.';
                        header.style.display = '';
                        frame.style.display = '';
                        dismiss_btn.style.display = '';
                        clearInterval(add_time_poll_interval);
                    }
                }, 2000);
            }
            /**
             * Load Schedule Extents
             */
            async function loadScheduleExtents(network_name) {
                const summary = await window.fs42Common.fetchScheduleSummary(network_name);
                if (summary && summary.extents) {
                    schedule_extents = summary.extents;
                    document.getElementById('start-date').value = summary.extents.start.replace(' ', 'T');
                    document.getElementById('end-date').value = summary.extents.end.replace(' ', 'T');
                }
            }
            /**
             * Get Schedule Blocks
             */
            async function getScheduleBlocks() {
                const start = document.getElementById('start-date').value;
                const end = document.getElementById('end-date').value;
                let blocks;
                if (!selected_station) {
                    return;
                }
                if (start && end) {
                    blocks = await window.fs42Common.fetchSchedule(selected_station, start, end);
                }
                else {
                    blocks = await window.fs42Common.fetchSchedule(selected_station);
                }
                if (blocks && blocks.length > 0) {
                    document.getElementById('schedule-blocks-header').style.display = '';
                }
                else {
                    document.getElementById('schedule-blocks-header').style.display = 'none';
                }
                document.getElementById('schedule-table').innerHTML =
                    window.fs42Common.renderScheduleTable(blocks);
            }

            // Event listeners
            document.getElementById('station-select').addEventListener('change', async function (e) {
                selected_station = e.target.value || 'all';
                updateStationSummary(selected_station);
                document.getElementById('schedule-table').innerHTML = '';
                document.getElementById('schedule-blocks-header').style.display = 'none';
                document.getElementById('add-time-log').textContent = '';
                document.getElementById('add-time-log-header').style.display = 'none';
                document.getElementById('add-time-log-frame').style.display = 'none';
                document.getElementById('add-time-log-dismiss').style.display = 'none';
                if (selected_station && selected_station !== 'all') {
                    await loadScheduleExtents(selected_station);

                    // Set default query to 24 hours from start of current hour
                    const now = new Date();
                    const start_of_hour = new Date(
                        now.getFullYear(),
                        now.getMonth(),
                        now.getDate(),
                        now.getHours(),
                        0,
                        0
                    );
                    const end_of_period = new Date(start_of_hour.getTime() + 24 * 60 * 60 * 1000); // +24 hours

                    // Format for datetime-local input (requires local time, not UTC)
                    const formatLocalDateTime = function (date) {
                        const year = date.getFullYear();
                        const month = String(date.getMonth() + 1).padStart(2, '0');
                        const day = String(date.getDate()).padStart(2, '0');
                        const hours = String(date.getHours()).padStart(2, '0');
                        const minutes = String(date.getMinutes()).padStart(2, '0');
                        return '' + year + '-' + month + '-' + day + 'T' + hours + ':' + minutes;
                    };
                    document.getElementById('start-date').value = formatLocalDateTime(start_of_hour);
                    document.getElementById('end-date').value = formatLocalDateTime(end_of_period);

                    // Auto-load schedule preview for the selected channel
                    await getScheduleBlocks();
                }
                else {
                    document.getElementById('start-date').value = '';
                    document.getElementById('end-date').value = '';
                }
            });
            document.getElementById('add-time-log-dismiss').addEventListener('click', function () {
                document.getElementById('add-time-log-frame').style.display = 'none';
                document.getElementById('add-time-log-dismiss').style.display = 'none';
            });
            document.getElementById('build-schedule-btn').addEventListener('click', async function () {
                const amount = document.getElementById('time-amount-select').value;
                const station = selected_station || 'all';
                const station_text = station === 'all' ? 'all stations' : station;
                document.getElementById('add-time-log').textContent =
                    'Starting add ' + amount + ' for ' + station_text + '...';
                document.getElementById('add-time-log-header').style.display = '';
                document.getElementById('add-time-log-frame').style.display = '';
                document.getElementById('add-time-log-dismiss').style.display = '';
                try {
                    const resp = await fetch('/build/schedule/add_time/' + amount + '/' + station, {
                        method: 'POST'
                    });
                    const data = await resp.json();
                    const task_id = data.task_id;
                    /**
                     * Poll Status
                     */
                    function pollStatus() {
                        if (add_time_poll_interval) {
                            clearInterval(add_time_poll_interval);
                        }
                        add_time_poll_interval = setInterval(async function () {
                            const resp = await fetch('/build/schedule/add_time/status/' + task_id);
                            const data = await resp.json();
                            document.getElementById('add-time-log').textContent = data.log || '';
                            if (data.status === 'done' || data.status === 'error') {
                                clearInterval(add_time_poll_interval);
                                if (selected_station && selected_station !== 'all') {
                                    await getScheduleBlocks();
                                }
                            }
                        }, 2000);
                    }
                    pollStatus();
                }
                catch (e) {
                    document.getElementById('add-time-log').textContent = 'Error starting add ' + amount + '.';
                }
            });
            document.getElementById('reset-schedules-btn').addEventListener('click', async function () {
                const station = selected_station || 'all';
                const station_text = station === 'all' ? 'all stations' : station;

                // Confirmation dialog
                const confirm_message =
                    station === 'all'
                        ? 'Are you sure you want to reset schedules for ALL stations? This will delete all existing schedule data.'
                        : 'Are you sure you want to reset the schedule for ' +
                          station +
                          '? This will delete all existing schedule data for this station.';
                if (!confirm(confirm_message)) {
                    return;
                }
                document.getElementById('add-time-log').textContent =
                    'Resetting schedules for ' + station_text + '...';
                document.getElementById('add-time-log-header').style.display = '';
                document.getElementById('add-time-log-frame').style.display = '';
                document.getElementById('add-time-log-dismiss').style.display = '';
                try {
                    const resp = await fetch('/build/schedule/reset/' + station, {
                        method: 'POST'
                    });
                    const data = await resp.json();
                    const task_id = data.task_id;
                    /**
                     * Poll Status
                     */
                    function pollStatus() {
                        if (add_time_poll_interval) {
                            clearInterval(add_time_poll_interval);
                        }
                        add_time_poll_interval = setInterval(async function () {
                            const resp = await fetch('/build/schedule/reset/status/' + task_id);
                            const data = await resp.json();
                            document.getElementById('add-time-log').textContent = data.log || '';
                            if (data.status === 'done' || data.status === 'error') {
                                clearInterval(add_time_poll_interval);
                                if (selected_station && selected_station !== 'all') {
                                    await getScheduleBlocks();
                                }
                            }
                        }, 2000);
                    }
                    pollStatus();
                }
                catch (e) {
                    document.getElementById('add-time-log').textContent = 'Error resetting schedules.';
                }
            });
            document.getElementById('get-schedule').addEventListener('click', getScheduleBlocks);
            loadStationsAndSummary();
        }

        // Search functionality
        /**
         * Setup Search Handlers
         */
        function setupSearchHandlers() {
            const search_btn = document.getElementById('search-btn');
            const clear_btn = document.getElementById('clear-search-btn');
            const search_input = document.getElementById('search-input');
            if (search_btn) {
                search_btn.addEventListener('click', performSearch);
            }
            if (clear_btn) {
                clear_btn.addEventListener('click', clearSearch);
            }
            if (search_input) {
                search_input.addEventListener('keypress', function (e) {
                    if (e.key === 'Enter') {
                        performSearch();
                    }
                });
            }
        }
        /**
         * Perform Search
         */
        async function performSearch() {
            const search_input = document.getElementById('search-input');
            const results_div = document.getElementById('search-results');
            const results_content = document.getElementById('search-results-content');
            const search_btn = document.getElementById('search-btn');
            const query = search_input.value.trim();
            if (!query) {
                alert('Please enter a search term');
                return;
            }

            // Show loading state
            search_btn.textContent = 'Searching...';
            search_btn.disabled = true;
            results_div.style.display = 'block';
            results_content.innerHTML = '<p>Searching all schedules...</p>';
            try {
                const response = await window.fs42Api.get(
                    'schedules/search_all?query=' + encodeURIComponent(query)
                );
                displaySearchResults(response, query);
            }
            catch (error) {
                results_content.innerHTML =
                    '<p style="color: red;">Error searching schedules: ' + error.message + '</p>';
            }
            finally {
                search_btn.textContent = 'Search';
                search_btn.disabled = false;
            }
        }
        /**
         * Display Search Results
         */
        function displaySearchResults(response, query) {
            const results_content = document.getElementById('search-results-content');
            const results = response.results || [];
            if (results.length === 0) {
                results_content.innerHTML = '<p>No results found for "' + query + '".</p>';
                return;
            }

            // Flatten all blocks and group by day
            const all_blocks = [];
            let total_results = 0;
            let station_count = 0;
            for (const station_result of results) {
                const blocks = station_result.schedule_blocks || [];
                if (blocks.length > 0) {
                    station_count++;
                    total_results += blocks.length;
                    for (const block of blocks) {
                        all_blocks.push({
                            ...block,
                            station_name: station_result.network_name
                        });
                    }
                }
            }
            if (total_results === 0) {
                results_content.innerHTML = '<p>No results found for "' + query + '".</p>';
                return;
            }

            // Group blocks by day
            const blocks_by_day = {};
            for (const block of all_blocks) {
                const start_time = new Date(block.start_time);
                const day_key = start_time.toISOString().split('T')[0]; // YYYY-MM-DD format
                const day_label = start_time.toLocaleDateString('en-US', {
                    weekday: 'long',
                    year: 'numeric',
                    month: 'long',
                    day: 'numeric'
                });
                if (!blocks_by_day[day_key]) {
                    blocks_by_day[day_key] = {
                        label: day_label,
                        blocks: []
                    };
                }
                blocks_by_day[day_key].blocks.push(block);
            }

            // Sort days and blocks within each day
            const sorted_days = Object.keys(blocks_by_day).sort();
            for (const day_key of sorted_days) {
                blocks_by_day[day_key].blocks.sort(function (a, b) {
                    return new Date(a.start_time) - new Date(b.start_time);
                });
            }

            // Generate HTML
            let html =
                '<p><strong>Found ' +
                total_results +
                ' results across ' +
                station_count +
                ' stations for "' +
                query +
                '"</strong></p>';
            for (const day_key of sorted_days) {
                const day_data = blocks_by_day[day_key];
                html += '<h4>' + day_data.label + ' (' + day_data.blocks.length + ' results)</h4>';
                html += renderScheduleTableWithStations(day_data.blocks);
            }
            results_content.innerHTML = html;
        }
        /**
         * Render Schedule Table With Stations
         */
        function renderScheduleTableWithStations(blocks) {
            if (!blocks.length) {
                return '<p>No schedule blocks found.</p>';
            }
            let html = '<table class="pure-table pure-table-horizontal" style="width:100%;margin-top:1em;">';
            html +=
                '<thead><tr><th>Start Time</th><th>End Time</th><th>Station</th><th>Title</th></tr></thead><tbody>';
            for (const block of blocks) {
                // Format time only (not date) for readability
                const start = block.start_time ? formatTimeOnly(block.start_time) : '';
                const end = block.end_time ? formatTimeOnly(block.end_time) : '';
                html +=
                    "<tr>\n            <td data-label='Start Time'>" +
                    start +
                    "</td>\n            <td data-label='End Time'>" +
                    end +
                    "</td>\n            <td data-label='Station'><strong>" +
                    block.station_name +
                    "</strong></td>\n            <td data-label='Title'>" +
                    (block.title || '') +
                    '</td>\n        </tr>';
            }
            html += '</tbody></table>';
            return html;
        }
        /**
         * Format Time Only
         */
        function formatTimeOnly(dt_str) {
            // Returns just the time portion in HH:MM format
            if (!dt_str) {
                return '';
            }
            const d = new Date(dt_str);
            if (isNaN(d.getTime())) {
                return dt_str;
            }
            const hh = String(d.getHours()).padStart(2, '0');
            const min = String(d.getMinutes()).padStart(2, '0');
            return '' + hh + ':' + min;
        }
        /**
         * Clear Search
         */
        function clearSearch() {
            const search_input = document.getElementById('search-input');
            const results_div = document.getElementById('search-results');
            const results_content = document.getElementById('search-results-content');
            search_input.value = '';
            results_div.style.display = 'none';
            results_content.innerHTML = '';
        }
        self.initializeSchedulePage = initializeSchedulePage;
        self.setupSearchHandlers = setupSearchHandlers;
        self.performSearch = performSearch;
        self.displaySearchResults = displaySearchResults;
        self.renderScheduleTableWithStations = renderScheduleTableWithStations;
        self.formatTimeOnly = formatTimeOnly;
        self.clearSearch = clearSearch;
    };
    return self;
})();
