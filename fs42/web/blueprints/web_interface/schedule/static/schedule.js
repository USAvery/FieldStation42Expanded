/*
This Source Code Form is subject to the Mozilla Public License, v. 2.0.
See https://mozilla.org/MPL/2.0/.
*/
window.app = window.app || {};
app.web_interface = app.web_interface || {};
app.web_interface.schedule = (function () {
    let self = {};

    let stations = [];
    let selected_station = null;
    let schedule_extents = {
        start: null,
        end: null
    };
    let add_time_poll_interval = null;
    const add_time_type = null;

    /**
     * Load Stations And Summary
     */
    self.loadStationsAndSummary = async function() {
        stations = await fetchStationSummary();
        const available = stations.filter(station => station._has_schedule);
        app.widgets.selector.instances['station-select'].setOptions(
            [{value: 'all', label: 'All Channels (' + available.length + ')'}].concat(
                available.map(station => ({value: station.network_name, label: station.network_name}))), 'all');
        selected_station = 'all';
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
    };
    /**
     * Update Station Summary
     */
    self.updateStationSummary = function(network_name) {
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
                renderSummaryTable([station]);
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
    };
    /**
     * Poll Add Time Status
     */
    self.pollAddTimeStatus = function(task_id, after_done_callback) {
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
                const resp = await fetchURL(urlFor('api.build.add_time_to_schedule_status', {task_id: task_id}));
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
    };
    /**
     * Load Schedule Extents
     */
    self.loadScheduleExtents = async function(network_name) {
        const summary = await fetchScheduleSummary(network_name);
        if (summary && summary.extents) {
            schedule_extents = summary.extents;
            document.getElementById('start-date').value = summary.extents.start.replace(' ', 'T');
            document.getElementById('end-date').value = summary.extents.end.replace(' ', 'T');
        }
    };
    /**
     * Get Schedule Blocks
     */
    self.getScheduleBlocks = async function() {
        const start = document.getElementById('start-date').value;
        const end = document.getElementById('end-date').value;
        let blocks;
        if (!selected_station) {
            return;
        }
        if (start && end) {
            blocks = await fetchSchedule(selected_station, start, end);
        }
        else {
            blocks = await fetchSchedule(selected_station);
        }
        if (blocks && blocks.length > 0) {
            document.getElementById('schedule-blocks-header').style.display = '';
        }
        else {
            document.getElementById('schedule-blocks-header').style.display = 'none';
        }
        document.getElementById('schedule-table').innerHTML =
            renderScheduleTable(blocks);
    };
    /**
     * Setup Search Handlers
     */
    self.setupSearchHandlers = function() {
        app.widgets.search.instances.search.bind(self.performSearch, self.clearSearch);
    };
    /**
     * Perform Search
     */
    self.performSearch = async function() {
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
        app.widgets.search.instances.search.busy(true);
        results_div.style.display = 'block';
        results_content.innerHTML = '<p>Searching all schedules...</p>';
        try {
            const response = await apiGet(
                urlFor('api.schedules.search_all_schedules') + '?query=' + encodeURIComponent(query)
            );
            self.displaySearchResults(response, query);
        }
        catch (error) {
            showError(results_content, error);
        }
        finally {
            app.widgets.search.instances.search.busy(false);
        }
    };
    /**
     * Display Search Results
     */
    self.displaySearchResults = function(response, query) {
        const results_content = document.getElementById('search-results-content');
        const results = response.results || [];
        if (results.length === 0) {
            results_content.textContent = 'No results found for "' + query + '".';
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
            results_content.textContent = 'No results found for "' + query + '".';
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
            escapeHtml(query) +
            '"</strong></p>';
        for (const day_key of sorted_days) {
            const day_data = blocks_by_day[day_key];
            html += '<h4>' + day_data.label + ' (' + day_data.blocks.length + ' results)</h4>';
            html += self.renderScheduleTableWithStations(day_data.blocks);
        }
        results_content.innerHTML = html;
    };
    /**
     * Render Schedule Table With Stations
     */
    self.renderScheduleTableWithStations = function(blocks) {
        if (!blocks.length) {
            return '<p>No schedule blocks found.</p>';
        }
        let html = '<table class="pure-table pure-table-horizontal" style="width:100%;margin-top:1em;">';
        html +=
            '<thead><tr><th>Start Time</th><th>End Time</th><th>Station</th><th>Title</th></tr></thead><tbody>';
        for (const block of blocks) {
            // Format time only (not date) for readability
            const start = block.start_time ? self.formatTimeOnly(block.start_time) : '';
            const end = block.end_time ? self.formatTimeOnly(block.end_time) : '';
            html +=
                "<tr>\n            <td data-label='Start Time'>" +
                escapeHtml(start) +
                "</td>\n            <td data-label='End Time'>" +
                escapeHtml(end) +
                "</td>\n            <td data-label='Station'><strong>" +
                escapeHtml(block.station_name) +
                "</strong></td>\n            <td data-label='Title'>" +
                escapeHtml((block.title || '')) +
                '</td>\n        </tr>';
        }
        html += '</tbody></table>';
        return html;
    };
    /**
     * Format Time Only
     */
    self.formatTimeOnly = function(dt_str) {
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
    };
    /**
     * Clear Search
     */
    self.clearSearch = function() {
        const search_input = document.getElementById('search-input');
        const results_div = document.getElementById('search-results');
        const results_content = document.getElementById('search-results-content');
        search_input.value = '';
        results_div.style.display = 'none';
        results_content.innerHTML = '';
    };

    /** Handle station-select change. */
    self.onStationSelectChange = async function(e) {
        selected_station = e.target.value || 'all';
        self.updateStationSummary(selected_station);
        document.getElementById('schedule-table').innerHTML = '';
        document.getElementById('schedule-blocks-header').style.display = 'none';
        document.getElementById('add-time-log').textContent = '';
        document.getElementById('add-time-log-header').style.display = 'none';
        document.getElementById('add-time-log-frame').style.display = 'none';
        document.getElementById('add-time-log-dismiss').style.display = 'none';
        if (selected_station && selected_station !== 'all') {
            await self.loadScheduleExtents(selected_station);

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
            await self.getScheduleBlocks();
        }
        else {
            document.getElementById('start-date').value = '';
            document.getElementById('end-date').value = '';
        }
    };

    /** Handle build-schedule-btn click. */
    self.onBuildScheduleBtnClick = async function() {
        const amount = document.getElementById('time-amount-select').value;
        const station = selected_station || 'all';
        const station_text = station === 'all' ? 'all stations' : station;
        document.getElementById('add-time-log').textContent =
            'Starting add ' + amount + ' for ' + station_text + '...';
        document.getElementById('add-time-log-header').style.display = '';
        document.getElementById('add-time-log-frame').style.display = '';
        document.getElementById('add-time-log-dismiss').style.display = '';
        try {
            const resp = await fetchURL(urlFor('api.build.add_time_to_schedule', {amount: amount, network_name: station}), {
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
                    const resp = await fetchURL(urlFor('api.build.add_time_to_schedule_status', {task_id: task_id}));
                    const data = await resp.json();
                    document.getElementById('add-time-log').textContent = data.log || '';
                    if (data.status === 'done' || data.status === 'error') {
                        clearInterval(add_time_poll_interval);
                        if (selected_station && selected_station !== 'all') {
                            await self.getScheduleBlocks();
                        }
                    }
                }, 2000);
            }
            pollStatus();
        }
        catch (e) {
            document.getElementById('add-time-log').textContent = 'Error starting add ' + amount + '.';
        }
    };

    /** Handle reset-schedules-btn click. */
    self.onResetSchedulesBtnClick = async function() {
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
            const resp = await fetchURL(urlFor('api.build.rebuild_schedule', {network_name: station}), {
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
                    const resp = await fetchURL(urlFor('api.build.rebuild_schedule_status', {task_id: task_id}));
                    const data = await resp.json();
                    document.getElementById('add-time-log').textContent = data.log || '';
                    if (data.status === 'done' || data.status === 'error') {
                        clearInterval(add_time_poll_interval);
                        if (selected_station && selected_station !== 'all') {
                            await self.getScheduleBlocks();
                        }
                    }
                }, 2000);
            }
            pollStatus();
        }
        catch (e) {
            document.getElementById('add-time-log').textContent = 'Error resetting schedules.';
        }
    };

    /** Bind page controls and load the initial data. */
    self.setup = async function() {
        // Set up search functionality
        self.setupSearchHandlers();
        /**
         * Initialize Schedule Page
         */

        // Event listeners
        document.getElementById('station-select').addEventListener('change', self.onStationSelectChange);
        document.getElementById('build-schedule-btn').addEventListener('click', self.onBuildScheduleBtnClick);
        document.getElementById('reset-schedules-btn').addEventListener('click', self.onResetSchedulesBtnClick);
        document.getElementById('get-schedule').addEventListener('click', self.getScheduleBlocks);
        self.loadStationsAndSummary();

    };
    return self;
})();
