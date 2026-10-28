/*
This Source Code Form is subject to the Mozilla Public License, v. 2.0.
See https://mozilla.org/MPL/2.0/.
*/
window.app = window.app || {};
app.web_interface = app.web_interface || {};
app.web_interface.catalog = (function () {
    let self = {};

    let stations = [];
    let selected_station = null;
    let rebuild_poll_interval = null;

    /**
     * Load Stations And Summary
     */
    self.loadStationsAndSummary = async function() {
        stations = await fetchStationSummary();
        const available = stations;
        app.widgets.selector.instances['station-select'].setOptions(
            [{value: 'all', label: 'All Channels (' + available.length + ')'}].concat(
                available.map(station => ({value: station.network_name, label: station.network_name}))), 'all');
        selected_station = 'all';
        document.getElementById('station-summary-table').innerHTML = '';
        document.getElementById('catalog-table').innerHTML = '';
        document.getElementById('rebuild-log').textContent = '';
    };
    /**
     * Update Station Summary
     */
    self.updateStationSummary = function(network_name) {
        const header = document.getElementById('station-summary-header');
        if (!network_name || network_name === 'all') {
            document.getElementById('station-summary-table').innerHTML = '';
            header.style.display = 'none';
            document.getElementById('catalog-table').innerHTML = '';
            document.getElementById('catalog-table-header').style.display = 'none';
            return;
        }
        const station = stations.find(function (s) {
            return s.network_name === network_name;
        });
        if (station) {
            document.getElementById('station-summary-table').innerHTML =
                renderSummaryTable([station]);
            header.style.display = '';
        }
        else {
            document.getElementById('station-summary-table').innerHTML = '<p>No summary found.</p>';
            header.style.display = 'none';
        }
    };
    /**
     * Load Catalog
     */
    self.loadCatalog = async function(network_name) {
        const entries = await fetchCatalog(network_name);
        const table = document.getElementById('catalog-table');
        const header = document.getElementById('catalog-table-header');
        if (entries && entries.length > 0) {
            table.innerHTML = renderCatalogTable(entries);
            header.style.display = '';
        }
        else {
            table.innerHTML = '';
            header.style.display = 'none';
        }
    };
    /**
     * Poll Rebuild Status
     */
    self.pollRebuildStatus = function(task_id, after_done_callback) {
        if (rebuild_poll_interval) {
            clearInterval(rebuild_poll_interval);
        }
        const log_elem = document.getElementById('rebuild-log');
        const header = document.getElementById('rebuild-log-header');
        const frame = document.getElementById('rebuild-log-frame');
        const dismiss_btn = document.getElementById('rebuild-log-dismiss');
        log_elem.textContent = 'Polling rebuild status...';
        header.style.display = '';
        frame.style.display = '';
        dismiss_btn.style.display = '';
        rebuild_poll_interval = setInterval(async function () {
            try {
                const resp = await fetchURL(urlFor('api.build.rebuild_catalog_status', {task_id: task_id}));
                const data = await resp.json();
                if (data.error) {
                    log_elem.textContent = data.error;
                    header.style.display = '';
                    frame.style.display = '';
                    dismiss_btn.style.display = '';
                    clearInterval(rebuild_poll_interval);
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
                    clearInterval(rebuild_poll_interval);
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
                clearInterval(rebuild_poll_interval);
            }
        }, 2000);
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
        results_content.innerHTML = '<p>Searching all catalogs...</p>';
        try {
            const response = await apiGet(
                urlFor('api.catalogs.search_all_catalogs') + '?query=' + encodeURIComponent(query)
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
        let total_results = 0;
        let html = '';
        for (const station_result of results) {
            const entries = station_result.catalog_entries || [];
            if (entries.length > 0) {
                total_results += entries.length;
                html += '<h4>' + escapeHtml(station_result.network_name) + ' (' + entries.length + ' results)</h4>';
                html += renderCatalogTable(entries);
            }
            else if (station_result.error) {
                html += '<h4>' + escapeHtml(station_result.network_name) + '</h4>';
                html += '<p style="color: red;">Error: ' + escapeHtml(station_result.error) + '</p>';
            }
        }
        if (total_results > 0) {
            results_content.innerHTML =
                '<p><strong>Found ' +
                total_results +
                ' results across ' +
                results.filter(function (r) {
                    return r.catalog_entries && r.catalog_entries.length > 0;
                }).length +
                ' stations for "' +
                escapeHtml(query) +
                '"</strong></p>' +
                html;
        }
        else {
            results_content.textContent = 'No results found for "' + query + '".';
        }
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
    self.onStationSelectChange = function(e) {
        selected_station = e.target.value || 'all';
        self.updateStationSummary(selected_station);
        document.getElementById('catalog-table').innerHTML = '';
        document.getElementById('catalog-table-header').style.display = 'none';
        document.getElementById('rebuild-log').textContent = '';
        document.getElementById('rebuild-log-header').style.display = 'none';
        document.getElementById('rebuild-log-frame').style.display = 'none';
        document.getElementById('rebuild-log-dismiss').style.display = 'none';
        if (selected_station && selected_station !== 'all') {
            self.loadCatalog(selected_station);
        }
    };

    /** Handle rebuild-btn click. */
    self.onRebuildBtnClick = async function() {
        const station = selected_station || 'all';
        const station_text = station === 'all' ? 'all catalogs' : station;
        document.getElementById('rebuild-log').textContent =
            'Starting rebuild for ' + station_text + '...';
        document.getElementById('rebuild-log-header').style.display = '';
        document.getElementById('catalog-table').innerHTML = '';
        document.getElementById('catalog-table-header').style.display = 'none';
        document.getElementById('station-summary-table').innerHTML = '';
        document.getElementById('station-summary-header').style.display = 'none';
        try {
            const resp = await fetchURL(urlFor('api.build.rebuild_catalog', {network_name: station}), {
                method: 'POST'
            });
            const data = await resp.json();
            if (data.task_id) {
                self.pollRebuildStatus(data.task_id, async function () {
                    // After rebuild is done, fetch and display catalog entries and update summary
                    if (selected_station && selected_station !== 'all') {
                        await self.loadCatalog(selected_station);
                        self.updateStationSummary(selected_station);
                    }
                });
            }
            else {
                document.getElementById('rebuild-log').textContent = 'Error starting rebuild.';
            }
        }
        catch (e) {
            document.getElementById('rebuild-log').textContent = 'Error starting rebuild.';
        }
    };

    /** Bind page controls and load the initial data. */
    self.setup = async function() {
        document.getElementById('station-select').addEventListener('change', self.onStationSelectChange);
        document.getElementById('rebuild-btn').addEventListener('click', self.onRebuildBtnClick);
        self.loadStationsAndSummary();

        // Set up search functionality
        self.setupSearchHandlers();

    };
    return self;
})();
