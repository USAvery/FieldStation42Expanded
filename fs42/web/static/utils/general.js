/*
This Source Code Form is subject to the Mozilla Public License, v. 2.0.
See https://mozilla.org/MPL/2.0/.
*/
window.app = window.app || {};
app.utils = app.utils || {};
app.utils.general = (function () {
    let self = {};

    /**
     * Init Theme
     */
    // common.js
    // Theme management
    function initTheme() {
        const saved_theme = localStorage.getItem('fs42-theme') || 'default';
        setTheme(saved_theme);
        if (document.getElementById('theme-select')) {
            document.getElementById('theme-select').value = saved_theme;
        }
    }
    /**
     * Set Theme
     */
    function setTheme(theme_name) {
        const theme_link = document.getElementById('theme-css');
        theme_link.href = '/static/themes/' + theme_name + '.css';
        localStorage.setItem('fs42-theme', theme_name);
    }

    // Menu management
    /**
     * Toggle Menu
     */
    function toggleMenu() {
        const menu = document.getElementById('mainMenu');
        menu.classList.toggle('pure-menu-active');
    }
    window.addEventListener('resize', function () {
        if (window.innerWidth >= 768) {
            const menu = document.getElementById('mainMenu');
            if (menu) {
                menu.classList.remove('pure-menu-active');
            }
        }
    });

    // Layout components
    /**
     * Create Main Menu
     */
    async function createMainMenu() {
        // Check if player queue is connected
        let player_menu_items = '';
        try {
            const response = await window.fs42Api.get('player/status/queue_connected');
            if (response.queue_connected) {
                player_menu_items =
                    '<li class="pure-menu-item"><a href="/static/remote.html" class="pure-menu-link">Remote</a></li>';
            }
        }
        catch (error) {
            console.log('Could not check player queue status:', error);
            // Don't show player menu if we can't connect
        }
        return (
            [
                '',
                '        <div class="pure-menu pure-menu-horizontal custom-menu" id="mainMenu">',
                '            <a href="#" class="pure-menu-heading">FieldStation42</a>',
                '            <span class="menu-toggle" onclick="window.fs42Common.toggleMenu()">&#9776;</span>',
                '            <ul class="pure-menu-list">',
                '                <li class="pure-menu-item"><a href="/" class="pure-menu-link">Home</a></li>',
                '                <li class="pure-menu-item"><a href="/static/catalog.html" class="pure-menu-link">Catalog</a></li>',
                '                <li class="pure-menu-item"><a href="/static/schedule.html" class="pure-menu-link">Schedule</a></li>',
                '                <li class="pure-menu-item"><a href="/static/guide.html" class="pure-menu-link">Guide</a></li>',
                '                <li class="pure-menu-item"><a href="/static/stations.html" class="pure-menu-link">Stations</a></li>',
                '                '
            ].join('\n') +
            player_menu_items +
            [
                '',
                '                <li class="pure-menu-item"><a href="/static/about.html" class="pure-menu-link">About</a></li>',
                '            </ul>',
                '        </div>',
                '    '
            ].join('\n')
        );
    }
    /**
     * Create Page Layout
     */
    async function createPageLayout(title, content) {
        const menu = await createMainMenu();
        return (
            '\n        ' +
            menu +
            '\n        <div class="pure-g">\n            <div class="pure-u-1">\n                <h1>' +
            title +
            '</h1>\n                ' +
            content +
            '\n            </div>\n        </div>\n    '
        );
    }
    /**
     * Create Station Selector
     */
    function createStationSelector() {
        return [
            '',
            '        <div id="station-select-frame" class="station-select-container">',
            '            <label for="station-select">Select Station:</label>',
            '            <select id="station-select" class="pure-input-1"></select>',
            '        </div>',
            '    '
        ].join('\n');
    }
    /**
     * Create Action Buttons
     */
    function createActionButtons(buttons) {
        const button_html = buttons
            .map(function (btn) {
                return (
                    '<button id="' +
                    btn.id +
                    '" class="pure-button ' +
                    (btn.classes || '') +
                    '">' +
                    btn.text +
                    '</button>'
                );
            })
            .join('');
        return '<div class="action-buttons">' + button_html + '</div>';
    }
    /**
     * Create Log Display
     */
    function createLogDisplay() {
        return [
            '',
            '        <div id="log-frame" class="log-container" style="display:none;">',
            '            <div class="log-header">',
            '                <h2 id="log-header-text">Log</h2>',
            '                <button id="log-dismiss" class="pure-button">Dismiss</button>',
            '            </div>',
            '            <pre id="log-content" class="fs42-terminal"></pre>',
            '        </div>',
            '    '
        ].join('\n');
    }

    // Fetch and display summary from /summary API
    /**
     * Fetch Station Summary
     */
    async function fetchStationSummary() {
        try {
            const resp = await window.fs42Api.get('summary');
            return resp.summary_data || [];
        }
        catch (e) {
            return [];
        }
    }
    /**
     * Fetch Channels
     */
    async function fetchChannels() {
        try {
            const resp = await window.fs42Api.get('summary/channels');
            return resp.channels || [];
        }
        catch (e) {
            return [];
        }
    }

    // Fetch catalog for a station
    /**
     * Fetch Catalog
     */
    async function fetchCatalog(network_id) {
        try {
            const resp = await window.fs42Api.get('catalogs/' + network_id);
            return resp.catalog_entries || [];
        }
        catch (e) {
            return [];
        }
    }

    // Render summary table (used in index.html)
    /**
     * Render Summary Table
     */
    function renderSummaryTable(stations) {
        if (!stations.length) {
            return '<p>No stations found.</p>';
        }
        let html = '<table class="pure-table pure-table-horizontal" style="width:100%;margin-top:1em;">';
        html +=
            '<thead><tr><th>Network</th><th>Catalog Entries</th><th>Total Duration</th><th>Schedule Start</th><th>Schedule End</th></tr></thead><tbody>';
        for (const station of stations) {
            const name = station.network_name || 'N/A';
            const entry_count = station.catalog_summary?.entry_count ?? 'N/A';
            let total_duration = station.catalog_summary?.total_duration ?? 'N/A';
            if (typeof total_duration === 'number') {
                total_duration = (total_duration / 3600).toFixed(2) + ' hrs';
            }
            const sched = station.schedule_summary || {};
            let start = sched.start ?? 'N/A';
            let end = sched.end ?? 'N/A';
            if (typeof start === 'string' && start.length > 10) {
                start = start.replace('T', ' ');
            }
            if (typeof end === 'string' && end.length > 10) {
                end = end.replace('T', ' ');
            }
            html +=
                "<tr>\n            <td data-label='Network'><strong>" +
                name +
                "</strong></td>\n            <td data-label='Catalog Entries'>" +
                entry_count +
                "</td>\n            <td data-label='Total Duration'>" +
                total_duration +
                "</td>\n            <td data-label='Schedule Start'>" +
                start +
                "</td>\n            <td data-label='Schedule End'>" +
                end +
                '</td>\n        </tr>';
        }
        html += '</tbody></table>';
        return html;
    }

    // Render catalog table
    /**
     * Render Catalog Table
     */
    function renderCatalogTable(entries) {
        if (!entries.length) {
            return '<p>No catalog entries found.</p>';
        }
        let html = '<table class="pure-table pure-table-horizontal" style="width:100%;margin-top:1em;">';
        html +=
            '<thead><tr><th>Title</th><th>Path</th><th>Duration</th><th>Count</th><th>Hints</th></tr></thead><tbody>';
        for (const entry of entries) {
            const hints = Array.isArray(entry.hints)
                ? entry.hints
                      .map(function (h) {
                          return JSON.stringify(h);
                      })
                      .join(', ')
                : '';
            const full_path = entry.path || '';
            const short_path = full_path.length > 100 ? full_path.slice(-100) : full_path;
            html +=
                "<tr>\n            <td data-label='Title'>" +
                entry.title +
                "</td>\n            <td data-label='Path'><span title=\"" +
                full_path +
                '">' +
                short_path +
                "</span></td>\n            <td data-label='Duration'>" +
                Number(entry.duration).toFixed(2) +
                "</td>\n            <td data-label='Count'>" +
                entry.count +
                "</td>\n            <td data-label='Hints'>" +
                hints +
                '</td>\n        </tr>';
        }
        html += '</tbody></table>';
        return html;
    }

    // Fetch schedule summary for extents
    /**
     * Fetch Schedule Summary
     */
    async function fetchScheduleSummary(network_id) {
        try {
            const resp = await window.fs42Api.get('summary/schedules/' + network_id);
            return resp;
        }
        catch (e) {
            return null;
        }
    }

    // Fetch schedule blocks for a station and date range
    /**
     * Fetch Schedule
     */
    async function fetchSchedule(network_id, start, end, include_meta) {
        try {
            let url = 'schedules/' + network_id;
            const params = [];
            if (start) {
                params.push('start=' + encodeURIComponent(start));
            }
            if (end) {
                params.push('end=' + encodeURIComponent(end));
            }
            if (include_meta) {
                params.push('include_meta=true');
            }
            if (params.length) {
                url += '?' + params.join('&');
            }
            const resp = await window.fs42Api.get(url);
            return resp.schedule_blocks || [];
        }
        catch (e) {
            return [];
        }
    }
    /**
     * Fetch Guide Schedules
     */
    async function fetchGuideSchedules(start, end, include_meta) {
        try {
            let url = 'schedules/all';
            const params = [];
            if (start) {
                params.push('start=' + encodeURIComponent(start));
            }
            if (end) {
                params.push('end=' + encodeURIComponent(end));
            }
            if (include_meta) {
                params.push('include_meta=true');
            }
            if (params.length) {
                url += '?' + params.join('&');
            }
            const resp = await window.fs42Api.get(url);
            return resp.schedules || {};
        }
        catch (e) {
            return {};
        }
    }

    // Render schedule table
    /**
     * Render Schedule Table
     */
    function renderScheduleTable(blocks) {
        if (!blocks.length) {
            return '<p>No schedule blocks found.</p>';
        }
        let html = '<table class="pure-table pure-table-horizontal" style="width:100%;margin-top:1em;">';
        html += '<thead><tr><th>Start Time</th><th>End Time</th><th>Title</th></tr></thead><tbody>';
        for (const block of blocks) {
            // Format date/time for human readability
            const start = block.start_time ? formatDateTime(block.start_time) : '';
            const end = block.end_time ? formatDateTime(block.end_time) : '';
            html +=
                "<tr>\n            <td data-label='Start Time'>" +
                start +
                "</td>\n            <td data-label='End Time'>" +
                end +
                "</td>\n            <td data-label='Title'>" +
                (block.title || '') +
                '</td>\n        </tr>';
        }
        html += '</tbody></table>';
        return html;
    }
    /**
     * Format Date Time
     */
    function formatDateTime(dt_str) {
        // Accepts ISO string, returns 'YYYY-MM-DD HH:MM' format
        if (!dt_str) {
            return '';
        }
        const d = new Date(dt_str);
        if (isNaN(d.getTime())) {
            return dt_str;
        }
        const yyyy = d.getFullYear();
        const mm = String(d.getMonth() + 1).padStart(2, '0');
        const dd = String(d.getDate()).padStart(2, '0');
        const hh = String(d.getHours()).padStart(2, '0');
        const min = String(d.getMinutes()).padStart(2, '0');
        return '' + yyyy + '-' + mm + '-' + dd + ' ' + hh + ':' + min;
    }
    self = {
        // Theme management
        initTheme,
        setTheme,
        // Menu and layout
        toggleMenu,
        createMainMenu,
        createPageLayout,
        createStationSelector,
        createActionButtons,
        createLogDisplay,
        // API functions
        fetchStationSummary,
        fetchChannels,
        fetchCatalog,
        renderSummaryTable,
        renderCatalogTable,
        fetchScheduleSummary,
        fetchSchedule,
        fetchGuideSchedules,
        renderScheduleTable
    };
    return self;
})();
window.fs42Common = app.utils.general;
