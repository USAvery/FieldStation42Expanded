/*
This Source Code Form is subject to the Mozilla Public License, v. 2.0.
See https://mozilla.org/MPL/2.0/.
*/
window.app = window.app || {};
app.web_interface = app.web_interface || {};
app.web_interface.stations = (function () {
    let self = {};

    let all_stations = [];
    let filtered_stations = [];

    /**
     * Load Stations
     */
    self.loadStations = async function() {
        try {
            const data = await apiGet('api.stations.list_stations');
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
            self.renderStations();
        }
        catch (error) {
            showError('station-list', error);
        }
    };
    /**
     * Apply Filters
     */
    self.applyFilters = function() {
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
        self.renderStations();
    };
    /**
     * Render Stations
     */
    self.renderStations = function() {
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
            const channel = escapeHtml(station.channel_number || 'N/A');
            const type = escapeHtml(station.network_type || 'standard');
            const description = self.getStationDescription(station);
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
                    '" onclick="app.web_interface.stations.editStation(this.dataset.name)">',
                    '                        Edit Config',
                    '                    </button>',
                    '                    <button class="pure-button" data-name="'
                ].join('\n') +
                escapeHtml(station.network_name) +
                [
                    '" onclick="app.web_interface.stations.duplicateStation(this.dataset.name)">',
                    '                        Duplicate',
                    '                    </button>',
                    '                </div>',
                    '            </div>',
                    '        '
                ].join('\n');
        }
        html += '</div>';
        container.innerHTML = html;
    };
    /**
     * Get Station Description
     */
    self.getStationDescription = function(station) {
        const type = escapeHtml(station.network_type || 'standard');
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
    };
    /**
     * Edit Station
     */
    self.editStation = function(network_name) {
        window.location.href = urlFor('/static/station_editor.html?station=' + encodeURIComponent(network_name));
    };
    /**
     * Escape Html
     */
    /**
     * Show Template Selector
     */
    self.showTemplateSelector = function() {
        document.getElementById('template-modal').style.display = 'flex';
    };
    /**
     * Hide Template Selector
     */
    self.hideTemplateSelector = function() {
        document.getElementById('template-modal').style.display = 'none';
    };
    /**
     * Create From Template
     */
    self.createFromTemplate = async function(template_name) {
        self.hideTemplateSelector();
        try {
            // Load the template
            const response = await fetchURL('/static/templates/' + template_name + '.json');
            if (!response.ok) {
                throw new Error('Failed to load template: ' + response.statusText);
            }
            const template = await response.json();

            // Suggest next available channel number
            const channel_number = await self.findNextAvailableChannel();
            template.station_conf.channel_number = channel_number;

            // Store template in sessionStorage and navigate to editor
            sessionStorage.setItem('newStationTemplate', JSON.stringify(template));
            window.location.href = urlFor('/static/station_editor.html?mode=create');
        }
        catch (error) {
            reportError(error);
        }
    };
    /**
     * Duplicate Station
     */
    self.duplicateStation = async function(network_name) {
        try {
            // Fetch the existing station
            const data = await apiGet(urlFor('api.stations.get_station_config', {network_name: network_name}));
            const config = data.station_config;

            // Create a copy with modified name and channel
            const new_name = self.generateDuplicateName(config.network_name);
            const new_channel = await self.findNextAvailableChannel();
            config.network_name = new_name;
            config.channel_number = new_channel;

            // Store in sessionStorage and navigate to editor
            sessionStorage.setItem('newStationTemplate', JSON.stringify(config));
            window.location.href = urlFor('/static/station_editor.html?mode=create');
        }
        catch (error) {
            reportError(error);
        }
    };
    /**
     * Generate Duplicate Name
     */
    self.generateDuplicateName = function(original_name) {
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
    };
    /**
     * Find Next Available Channel
     */
    self.findNextAvailableChannel = async function() {
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
    };

    /** Bind page controls and load the initial data. */
    self.setup = async function() {
        // Load stations
        await self.loadStations();

        // Setup event listeners
        document.getElementById('type-filter').addEventListener('change', self.applyFilters);
        document.getElementById('search-input').addEventListener('input', self.applyFilters);

        // Template selector modal functions
    };
    self.escapeHtml = escapeHtml;
    return self;
})();
