/*
This Source Code Form is subject to the Mozilla Public License, v. 2.0.
See https://mozilla.org/MPL/2.0/.
*/
window.app = window.app || {};
app.tools = app.tools || {};
app.tools.catalog = (function () {
    let self = {};
    /**
     * Set up the catalog page
     */
    self.setup = function () {
        // Initialize page layout
        document.addEventListener('DOMContentLoaded', async function () {
            window.fs42Common.initTheme();
            const log_display = window.fs42Common.createLogDisplay();
            const content =
                [
                    '',
                    '            <div id="search-section" class="pure-u-1" style="margin-bottom: 1em;">',
                    '                <div class="pure-form" style="display: flex; align-items: center; gap: 0.5em;">',
                    '                    <input type="text" id="search-input" placeholder="Search catalogs..." class="pure-input" style="flex: 1; max-width: 300px;">',
                    '                    <button id="search-btn" class="pure-button pure-button-primary">Search</button>',
                    '                    <button id="clear-search-btn" class="pure-button">Clear</button>',
                    '                </div>',
                    '                <div id="search-results" style="margin-top: 1em; display: none;">',
                    '                    <h3>Search Results</h3>',
                    '                    <div id="search-results-content"></div>',
                    '                </div>',
                    '            </div>',
                    '            <div class="station-select-container">',
                    '                <label for="station-select">Select Station:</label>',
                    '                <select id="station-select" class="pure-input-1"></select>',
                    '                <button id="rebuild-btn" class="pure-button primary" style="margin-left: 1em;">Rebuild Catalog</button>',
                    '            </div>',
                    '            <div id="station-summary" class="pure-u-1">',
                    '                <h2 id="station-summary-header" style="display:none;">Station Summary</h2>',
                    '                <div id="station-summary-table"></div>',
                    '            </div>',
                    '            '
                ].join('\n') +
                log_display
                    .replace('log-frame', 'rebuild-log-frame')
                    .replace('log-header-text', 'rebuild-log-header')
                    .replace('log-dismiss', 'rebuild-log-dismiss')
                    .replace('log-content', 'rebuild-log') +
                [
                    '',
                    '            <div id="catalog-table-frame" class="pure-u-1">',
                    '                <h2 id="catalog-table-header" style="display:none;">Catalog Entries</h2>',
                    '                <div id="catalog-table"></div>',
                    '            </div>',
                    '        '
                ].join('\n');
            document.body.innerHTML = await window.fs42Common.createPageLayout('Catalog Manager', content);
        });

        // Declare variables in global scope
        let stations = [];
        let selected_station = null;
        let rebuild_poll_interval = null;

        // Wait for DOM to be ready before adding event listeners
        document.addEventListener('DOMContentLoaded', async function () {
            // Wait for the page layout to be created first
            await new Promise(function (resolve) {
                const checkElements = function () {
                    if (document.getElementById('station-select')) {
                        resolve();
                    }
                    else {
                        setTimeout(checkElements, 10);
                    }
                };
                checkElements();
            });
            /**
             * Load Stations And Summary
             */
            async function loadStationsAndSummary() {
                stations = await window.fs42Common.fetchStationSummary();
                const select = document.getElementById('station-select');
                select.innerHTML = '';
                const all_opt = document.createElement('option');
                all_opt.value = 'all';
                all_opt.textContent = 'All Channels (' + stations.length + ')';
                select.appendChild(all_opt);
                stations.forEach(function (station) {
                    const opt = document.createElement('option');
                    opt.value = station.network_name;
                    opt.textContent = station.network_name;
                    select.appendChild(opt);
                });
                selected_station = 'all';
                select.value = 'all';
                document.getElementById('station-summary-table').innerHTML = '';
                document.getElementById('catalog-table').innerHTML = '';
                document.getElementById('rebuild-log').textContent = '';
            }
            /**
             * Update Station Summary
             */
            function updateStationSummary(network_name) {
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
                        window.fs42Common.renderSummaryTable([station]);
                    header.style.display = '';
                }
                else {
                    document.getElementById('station-summary-table').innerHTML = '<p>No summary found.</p>';
                    header.style.display = 'none';
                }
            }
            /**
             * Load Catalog
             */
            async function loadCatalog(network_name) {
                const entries = await window.fs42Common.fetchCatalog(network_name);
                const table = document.getElementById('catalog-table');
                const header = document.getElementById('catalog-table-header');
                if (entries && entries.length > 0) {
                    table.innerHTML = window.fs42Common.renderCatalogTable(entries);
                    header.style.display = '';
                }
                else {
                    table.innerHTML = '';
                    header.style.display = 'none';
                }
            }
            /**
             * Poll Rebuild Status
             */
            function pollRebuildStatus(task_id, after_done_callback) {
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
                        const resp = await fetch('/build/catalog/status/' + task_id);
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
            }
            document.getElementById('station-select').addEventListener('change', function (e) {
                selected_station = e.target.value || 'all';
                updateStationSummary(selected_station);
                document.getElementById('catalog-table').innerHTML = '';
                document.getElementById('catalog-table-header').style.display = 'none';
                document.getElementById('rebuild-log').textContent = '';
                document.getElementById('rebuild-log-header').style.display = 'none';
                document.getElementById('rebuild-log-frame').style.display = 'none';
                document.getElementById('rebuild-log-dismiss').style.display = 'none';
                if (selected_station && selected_station !== 'all') {
                    loadCatalog(selected_station);
                }
            });
            document.getElementById('rebuild-log-dismiss').addEventListener('click', function () {
                document.getElementById('rebuild-log-frame').style.display = 'none';
                document.getElementById('rebuild-log-dismiss').style.display = 'none';
            });
            document.getElementById('rebuild-btn').addEventListener('click', async function () {
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
                    const resp = await fetch('/build/catalog/' + station, {
                        method: 'POST'
                    });
                    const data = await resp.json();
                    if (data.task_id) {
                        pollRebuildStatus(data.task_id, async function () {
                            // After rebuild is done, fetch and display catalog entries and update summary
                            if (selected_station && selected_station !== 'all') {
                                await loadCatalog(selected_station);
                                updateStationSummary(selected_station);
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
            });
            loadStationsAndSummary();

            // Set up search functionality
            setupSearchHandlers();

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
                results_content.innerHTML = '<p>Searching all catalogs...</p>';
                try {
                    const response = await window.fs42Api.get(
                        'catalogs/search_all?query=' + encodeURIComponent(query)
                    );
                    displaySearchResults(response, query);
                }
                catch (error) {
                    results_content.innerHTML =
                        '<p style="color: red;">Error searching catalogs: ' + error.message + '</p>';
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
                let total_results = 0;
                let html = '';
                for (const station_result of results) {
                    const entries = station_result.catalog_entries || [];
                    if (entries.length > 0) {
                        total_results += entries.length;
                        html += '<h4>' + station_result.network_name + ' (' + entries.length + ' results)</h4>';
                        html += window.fs42Common.renderCatalogTable(entries);
                    }
                    else if (station_result.error) {
                        html += '<h4>' + station_result.network_name + '</h4>';
                        html += '<p style="color: red;">Error: ' + station_result.error + '</p>';
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
                        query +
                        '"</strong></p>' +
                        html;
                }
                else {
                    results_content.innerHTML = '<p>No results found for "' + query + '".</p>';
                }
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
        }); // Close DOMContentLoaded event handler
    };
    return self;
})();
