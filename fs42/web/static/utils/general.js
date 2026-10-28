/*
This Source Code Form is subject to the Mozilla Public License, v. 2.0.
See https://mozilla.org/MPL/2.0/.
*/
/** Escape display data before combining it with trusted layout markup. */
function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
}

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
    theme_link.href = urlFor('/static/themes/' + theme_name + '.css');
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

/**
 * Initialize the console theme and player-dependent navigation
 */
async function initConsole() {
    initTheme();
    const items = document.querySelectorAll('[data-requires-player]');
    if (!items.length) {
        return;
    }
    try {
        const status = await apiGet('api.player.get_connected');
        for (const item of items) {
            item.hidden = !status.queue_connected;
        }
    }
    catch (error) {
        console.log('Could not check player queue status:', error);
    }
}

// Fetch and display summary from /summary API
/**
 * Fetch Station Summary
 */
async function fetchStationSummary() {
    try {
        const resp = await apiGet('api.summary.get_summary');
        return resp.summary_data || [];
    }
    catch (e) {
        reportError(e);
        return [];
    }
}
/**
 * Fetch Channels
 */
async function fetchChannels() {
    try {
        const resp = await apiGet('api.summary.get_channels');
        return resp.channels || [];
    }
    catch (e) {
        reportError(e);
        return [];
    }
}

// Fetch catalog for a station
/**
 * Fetch Catalog
 */
async function fetchCatalog(network_id) {
    try {
        const resp = await apiGet(urlFor('api.catalogs.get_catalog', {network_name: network_id}));
        return resp.catalog_entries || [];
    }
    catch (e) {
        reportError(e);
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
            escapeHtml(name) +
            "</strong></td>\n            <td data-label='Catalog Entries'>" +
            escapeHtml(entry_count) +
            "</td>\n            <td data-label='Total Duration'>" +
            escapeHtml(total_duration) +
            "</td>\n            <td data-label='Schedule Start'>" +
            escapeHtml(start) +
            "</td>\n            <td data-label='Schedule End'>" +
            escapeHtml(end) +
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
            escapeHtml(entry.title) +
            "</td>\n            <td data-label='Path'><span title=\"" +
            escapeHtml(full_path) +
            '">' +
            escapeHtml(short_path) +
            "</span></td>\n            <td data-label='Duration'>" +
            Number(entry.duration).toFixed(2) +
            "</td>\n            <td data-label='Count'>" +
            escapeHtml(entry.count) +
            "</td>\n            <td data-label='Hints'>" +
            escapeHtml(hints) +
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
        const resp = await apiGet(urlFor('api.summary.get_schedule_summary', {network_name: network_id}));
        return resp;
    }
    catch (e) {
        reportError(e);
        return null;
    }
}

// Fetch schedule blocks for a station and date range
/**
 * Fetch Schedule
 */
async function fetchSchedule(network_id, start, end, include_meta) {
    try {
        let url = urlFor('api.schedules.get_schedule', {network_name: network_id});
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
        const resp = await apiGet(url);
        return resp.schedule_blocks || [];
    }
    catch (e) {
        reportError(e);
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
        const resp = await apiGet(url);
        return resp.schedules || {};
    }
    catch (e) {
        reportError(e);
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
            escapeHtml(start) +
            "</td>\n            <td data-label='End Time'>" +
            escapeHtml(end) +
            "</td>\n            <td data-label='Title'>" +
            escapeHtml((block.title || '')) +
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
