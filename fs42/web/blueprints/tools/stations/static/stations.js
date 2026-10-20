/*
This Source Code Form is subject to the Mozilla Public License, v. 2.0.
See https://mozilla.org/MPL/2.0/.
*/
window.app = window.app || {};
app.tools = app.tools || {};
app.tools.stations = (function () {
    let self = {};
    /**
     * Set up the stations page
     */
    self.setup = function () {
        let all_stations = [];
        let filtered_stations = [];

        // Initialize page layout
        document.addEventListener('DOMContentLoaded', async function () {
            window.fs42Common.initTheme();
            const content = [
                '',
                '        <div class="page-header">',
                '            <div>',
                '                <h1 style="margin:0;">Station Manager</h1>',
                '                <p style="color:#8b949e;margin:0.5em 0 0 0;">Manage your FieldStation42 channel configurations</p>',
                '            </div>',
                '            <button class="pure-button pure-button-primary" onclick="app.tools.stations.showTemplateSelector()">',
                '                + Create New Station',
                '            </button>',
                '        </div>',
                '',
                '        <div class="filter-bar">',
                '            <select id="type-filter" class="pure-input">',
                '                <option value="all">All Types</option>',
                '                <option value="standard">Standard</option>',
                '                <option value="web">Web</option>',
                '                <option value="guide">Guide</option>',
                '                <option value="loop">Loop</option>',
                '                <option value="streaming">Streaming</option>',
                '            </select>',
                '            <div class="search-container">',
                '                <input id="search-input" type="text" class="pure-input" placeholder="Search stations...">',
                '                <span class="search-icon">🔍</span>',
                '            </div>',
                '        </div>',
                '',
                '        <div id="station-list">',
                '            <div class="loading-spinner">',
                '                <p>Loading stations...</p>',
                '            </div>',
                '        </div>',
                '',
                '        <!-- Template Selector Modal -->',
                '        <div id="template-modal" class="modal" style="display:none;">',
                '            <div class="modal-overlay" onclick="app.tools.stations.hideTemplateSelector()"></div>',
                '            <div class="modal-content">',
                '                <div class="modal-header">',
                '                    <h2>Create New Station</h2>',
                '                    <button class="modal-close" onclick="app.tools.stations.hideTemplateSelector()">×</button>',
                '                </div>',
                '                <div class="modal-body">',
                '                    <p style="color:#8b949e;margin-bottom:1.5em;">Choose a template to get started:</p>',
                '                    <div class="template-grid">',
                '                        <div class="template-card" onclick="app.tools.stations.createFromTemplate(\'standard\')">',
                '                            <div class="template-icon">📺</div>',
                '                            <h3>Standard</h3>',
                '                            <p>Traditional scheduled TV with time slots and programming</p>',
                '                        </div>',
                '                        <div class="template-card" onclick="app.tools.stations.createFromTemplate(\'web\')">',
                '                            <div class="template-icon">🌐</div>',
                '                            <h3>Web Page</h3>',
                '                            <p>Embed a web page as a channel</p>',
                '                        </div>',
                '                        <div class="template-card" onclick="app.tools.stations.createFromTemplate(\'loop\')">',
                '                            <div class="template-icon">🔄</div>',
                '                            <h3>Loop</h3>',
                '                            <p>Continuous playlist of content</p>',
                '                        </div>',
                '                        <div class="template-card" onclick="app.tools.stations.createFromTemplate(\'guide\')">',
                '                            <div class="template-icon">📋</div>',
                '                            <h3>Guide</h3>',
                '                            <p>Scrolling guide with programming schedule</p>',
                '                        </div>',
                '                        <div class="template-card" onclick="app.tools.stations.createFromTemplate(\'streaming\')">',
                '                            <div class="template-icon">📡</div>',
                '                            <h3>Streaming</h3>',
                '                            <p>External stream sources</p>',
                '                        </div>',
                '                        <div class="template-card" onclick="app.tools.stations.createFromTemplate(\'blank\')">',
                '                            <div class="template-icon">⚡</div>',
                '                            <h3>Blank</h3>',
                '                            <p>Minimal configuration for advanced users</p>',
                '                        </div>',
                '                    </div>',
                '                </div>',
                '            </div>',
                '        </div>',
                '    '
            ].join('\n');
            document.body.innerHTML = await window.fs42Common.createPageLayout('', content);

            // Load stations
            await loadStations();

            // Setup event listeners
            document.getElementById('type-filter').addEventListener('change', applyFilters);
            document.getElementById('search-input').addEventListener('input', applyFilters);
        });
        /**
         * Load Stations
         */
        async function loadStations() {
            try {
                const data = await window.fs42Api.get('stations');
                // Extract station_conf from each station object
                all_stations = (data.stations || []).map(function (s) {
                    return s.station_conf;
                });
                filtered_stations = [...all_stations];

                // Sort by channel number
                all_stations.sort(function (a, b) {
                    return (a.channel_number || 0) - (b.channel_number || 0);
                });
                filtered_stations.sort(function (a, b) {
                    return (a.channel_number || 0) - (b.channel_number || 0);
                });
                renderStations();
            }
            catch (error) {
                document.getElementById('station-list').innerHTML =
                    '\n            <div class="error-message">\n                <strong>Error loading stations:</strong> ' +
                    (error.message || 'Unknown error') +
                    '\n            </div>\n        ';
            }
        }
        /**
         * Apply Filters
         */
        function applyFilters() {
            const type_filter = document.getElementById('type-filter').value;
            const search_query = document.getElementById('search-input').value.toLowerCase();
            filtered_stations = all_stations.filter(function (station) {
                // Type filter
                if (type_filter !== 'all' && (station.network_type || 'standard') !== type_filter) {
                    return false;
                }

                // Search filter
                if (search_query) {
                    const name_match = (station.network_name || '').toLowerCase().includes(search_query);
                    const channel_match = String(station.channel_number || '').includes(search_query);
                    if (!name_match && !channel_match) {
                        return false;
                    }
                }
                return true;
            });
            renderStations();
        }
        /**
         * Render Stations
         */
        function renderStations() {
            const container = document.getElementById('station-list');
            if (filtered_stations.length === 0) {
                container.innerHTML = [
                    '',
                    '            <div class="empty-state">',
                    '                <h3>No stations found</h3>',
                    '                <p>Try adjusting your filters or search query.</p>',
                    '            </div>',
                    '        '
                ].join('\n');
                return;
            }
            let html = '<div class="station-cards">';
            for (const station of filtered_stations) {
                const name = escapeHtml(station.network_name || 'Unnamed Station');
                const channel = station.channel_number || 'N/A';
                const type = station.network_type || 'standard';
                const description = getStationDescription(station);
                const draft_badge = station._draft
                    ? '<span class="station-card-draft">draft &bull; not on air</span>'
                    : '';
                const draft_reason = station._draft
                    ? '<div class="station-card-draft-reason">' +
                      escapeHtml(station._draft_reason || 'Configuration could not be loaded') +
                      '</div>'
                    : '';
                html +=
                    [
                        '',
                        '            <div class="station-card">',
                        '                <div class="station-card-header">',
                        '                    <div class="station-card-title-row">',
                        '                        <h3 class="station-card-name">'
                    ].join('\n') +
                    name +
                    '</h3>\n                        <span class="station-card-channel">#' +
                    channel +
                    [
                        '</span>',
                        '                    </div>',
                        '                    <div class="station-card-meta">',
                        '                        <span class="station-card-type station-type-'
                    ].join('\n') +
                    type +
                    '">' +
                    type +
                    '</span>\n                        ' +
                    draft_badge +
                    '\n                    </div>\n                </div>\n                <div class="station-card-description">' +
                    description +
                    '</div>\n                ' +
                    draft_reason +
                    [
                        '',
                        '                <div class="station-card-actions">',
                        '                    <button class="pure-button pure-button-primary" data-name="'
                    ].join('\n') +
                    escapeHtml(station.network_name) +
                    [
                        '" onclick="app.tools.stations.editStation(this.dataset.name)">',
                        '                        Edit Config',
                        '                    </button>',
                        '                    <button class="pure-button" data-name="'
                    ].join('\n') +
                    escapeHtml(station.network_name) +
                    [
                        '" onclick="app.tools.stations.duplicateStation(this.dataset.name)">',
                        '                        Duplicate',
                        '                    </button>',
                        '                </div>',
                        '            </div>',
                        '        '
                    ].join('\n');
            }
            html += '</div>';
            container.innerHTML = html;
        }
        /**
         * Get Station Description
         */
        function getStationDescription(station) {
            const type = station.network_type || 'standard';
            switch (type) {
                case 'standard':
                    const increment = station.schedule_increment || 30;
                    const commercial = station.commercial_free ? 'Commercial-free' : 'With commercials';
                    return '' + commercial + ' &bull; ' + increment + '-min intervals';
                case 'web':
                    const url = station.web_url || 'No URL set';
                    return 'Web page channel<br><small style="color:#61afef;">' + escapeHtml(url) + '</small>';
                case 'guide':
                    const messages = station.messages?.length || 0;
                    const images = station.images?.length || 0;
                    return 'Program guide &bull; ' + messages + ' message(s) &bull; ' + images + ' image(s)';
                case 'loop':
                    const dir = station.content_dir || 'No directory set';
                    return 'Continuous loop<br><small style="color:#61afef;">' + escapeHtml(dir) + '</small>';
                case 'streaming':
                    const streams = station.streams?.length || 0;
                    return 'External streams &bull; ' + streams + ' source(s)';
                default:
                    return 'Custom configuration';
            }
        }
        /**
         * Edit Station
         */
        function editStation(network_name) {
            window.location.href = 'station_editor.html?station=' + encodeURIComponent(network_name);
        }
        /**
         * Escape Html
         */
        function escapeHtml(text) {
            if (!text) {
                return '';
            }
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        // Template selector modal functions
        /**
         * Show Template Selector
         */
        function showTemplateSelector() {
            document.getElementById('template-modal').style.display = 'flex';
        }
        /**
         * Hide Template Selector
         */
        function hideTemplateSelector() {
            document.getElementById('template-modal').style.display = 'none';
        }
        /**
         * Create From Template
         */
        async function createFromTemplate(template_name) {
            hideTemplateSelector();
            try {
                // Load the template
                const response = await fetch('/static/templates/' + template_name + '.json');
                if (!response.ok) {
                    throw new Error('Failed to load template: ' + response.statusText);
                }
                const template = await response.json();

                // Suggest next available channel number
                const channel_number = await findNextAvailableChannel();
                template.station_conf.channel_number = channel_number;

                // Store template in sessionStorage and navigate to editor
                sessionStorage.setItem('newStationTemplate', JSON.stringify(template));
                window.location.href = 'station_editor.html?mode=create';
            }
            catch (error) {
                alert('Error loading template: ' + error.message);
            }
        }
        /**
         * Duplicate Station
         */
        async function duplicateStation(network_name) {
            try {
                // Fetch the existing station
                const data = await window.fs42Api.get('stations/' + encodeURIComponent(network_name));
                const config = data.station_config;

                // Create a copy with modified name and channel
                const new_name = generateDuplicateName(config.network_name);
                const new_channel = await findNextAvailableChannel();
                config.network_name = new_name;
                config.channel_number = new_channel;

                // Store in sessionStorage and navigate to editor
                sessionStorage.setItem('newStationTemplate', JSON.stringify(config));
                window.location.href = 'station_editor.html?mode=create';
            }
            catch (error) {
                alert('Error duplicating station: ' + error.message);
            }
        }
        /**
         * Generate Duplicate Name
         */
        function generateDuplicateName(original_name) {
            // Check if name already ends with " 2", " 3", etc.
            const match = original_name.match(/^(.*?)\s+(\d+)$/);
            if (match) {
                const base_name = match[1];
                let num = parseInt(match[2]);

                // Find next available number
                while (
                    all_stations.some(function (s) {
                        return s.network_name === '' + base_name + ' ' + num;
                    })
                ) {
                    num++;
                }
                return '' + base_name + ' ' + num;
            }
            else {
                // No number suffix, try " 2"
                if (
                    !all_stations.some(function (s) {
                        return s.network_name === '' + original_name + ' 2';
                    })
                ) {
                    return '' + original_name + ' 2';
                }

                // " 2" exists, find next available
                let num = 3;
                while (
                    all_stations.some(function (s) {
                        return s.network_name === '' + original_name + ' ' + num;
                    })
                ) {
                    num++;
                }
                return '' + original_name + ' ' + num;
            }
        }
        /**
         * Find Next Available Channel
         */
        async function findNextAvailableChannel() {
            const used_channels = all_stations.map(function (s) {
                return s.channel_number;
            });

            // Find first available channel starting from 1
            for (let i = 1; i < 1000; i++) {
                if (!used_channels.includes(i)) {
                    return i;
                }
            }
            return 999; // Fallback
        }
        self.loadStations = loadStations;
        self.applyFilters = applyFilters;
        self.renderStations = renderStations;
        self.getStationDescription = getStationDescription;
        self.editStation = editStation;
        self.escapeHtml = escapeHtml;
        self.showTemplateSelector = showTemplateSelector;
        self.hideTemplateSelector = hideTemplateSelector;
        self.createFromTemplate = createFromTemplate;
        self.duplicateStation = duplicateStation;
        self.generateDuplicateName = generateDuplicateName;
        self.findNextAvailableChannel = findNextAvailableChannel;
    };
    return self;
})();
