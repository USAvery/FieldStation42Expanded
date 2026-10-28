/*
This Source Code Form is subject to the Mozilla Public License, v. 2.0.
See https://mozilla.org/MPL/2.0/.
*/
window.app = window.app || {};
app.web_interface = app.web_interface || {};
app.web_interface.index = (function () {
    let self = {};
    const escapeHtml = app.utils.general.escapeHtml;

    /**
     * Load Station Summary
     */
    async function loadStationSummary() {
        try {
            const resp = await window.fs42Api.get('api.summary.get_summary');
            const stations = resp.summary_data || [];
            if (stations.length === 0) {
                document.getElementById('stations-list').innerHTML = '<p>No stations found.</p>';
                return;
            }
            let html = '<table class="pure-table pure-table-horizontal" style="width:100%;margin-top:1em;">';
            html +=
                '<thead><tr><th>Network</th><th>Channel</th><th>Catalog Entries</th><th>Total Duration</th><th>Schedule Start</th><th>Schedule End</th></tr></thead><tbody>';
            for (const station of stations) {
                const name = station.network_name || 'N/A';
                const channel = station.channel_number || 'N/A';
                const entry_count = station.catalog_summary?.entry_count ?? 'N/A';
                let total_duration = station.catalog_summary?.total_duration ?? 'N/A';
                // Convert totalDuration from seconds to hours (rounded to 2 decimals)
                if (typeof total_duration === 'number') {
                    total_duration = (total_duration / 3600).toFixed(2) + ' hrs';
                }
                const sched = station.schedule_summary || {};
                let start, end;

                // Check if station has schedule configured
                if (!station._has_schedule) {
                    // No schedule configured for this station
                    start = 'N/A';
                    end = 'N/A';
                }
                else if (sched.start === 0 || sched.end === 0) {
                    // Station has schedule configured but it's empty
                    start = '-';
                    end = '-';
                }
                else {
                    // Station has schedule with data
                    start = sched.start ?? '-';
                    end = sched.end ?? '-';
                    // Format start/end if they look like ISO strings
                    if (typeof start === 'string' && start.length > 10) {
                        start = start.replace('T', ' ');
                    }
                    if (typeof end === 'string' && end.length > 10) {
                        end = end.replace('T', ' ');
                    }
                    // Remove last ':00' from start/end if present
                    if (typeof start === 'string' && start.match(/:\d{2}$/)) {
                        start = start.replace(/:\d{2}$/, '');
                    }
                    if (typeof end === 'string' && end.match(/:\d{2}$/)) {
                        end = end.replace(/:\d{2}$/, '');
                    }
                }
                html +=
                    "<tr>\n                <td data-label='Network'><strong>" +
                    escapeHtml(name) +
                    "</strong></td>\n                <td data-label='Channel'>" +
                    escapeHtml(channel) +
                    "</td>\n                <td data-label='Catalog Entries'>" +
                    escapeHtml(entry_count) +
                    "</td>\n                <td data-label='Total Duration'>" +
                    escapeHtml(total_duration) +
                    "</td>\n                <td data-label='Schedule Start'>" +
                    escapeHtml(start) +
                    "</td>\n                <td data-label='Schedule End'>" +
                    escapeHtml(end) +
                    '</td>\n            </tr>';
            }
            html += '</tbody></table>';
            document.getElementById('stations-list').innerHTML = html;
        }
        catch (e) {
            document.getElementById('stations-list').innerHTML =
                '<p style="color:red">Failed to load station data.</p>';
        }
    }
    /**
     * Check Queue Connection
     */
    async function checkQueueConnection() {
        try {
            const resp = await window.fs42Api.get('api.player.get_connected');
            const ticker_control = document.getElementById('ticker-control');
            if (resp.queue_connected) {
                ticker_control.style.display = 'block';
            }
            else {
                ticker_control.style.display = 'none';
            }
        }
        catch (e) {
            // If API call fails, hide ticker controls
            document.getElementById('ticker-control').style.display = 'none';
        }
    }
    /**
     * Update Station Summary
     */
    function updateStationSummary(network_name) {
        if (!network_name) {
            document.getElementById('station-summary-table').innerHTML = '';
            document.getElementById('catalog-table').innerHTML = '';
            return;
        }
        const station = stations.find(function (s) {
            return s.network_name === network_name;
        });
        if (station) {
            document.getElementById('station-summary-table').innerHTML = window.fs42Common.renderSummaryTable([
                station
            ]);
        }
        else {
            document.getElementById('station-summary-table').innerHTML = '<p>No summary found.</p>';
        }
    }

    /** Bind page controls and load the initial data. */
    self.setup = async function() {
        // Load page data after its controls have been added to the document
        await loadStationSummary();
        await checkQueueConnection();
        setInterval(checkQueueConnection, 5000);

        // Handle ticker form submission
        document.addEventListener('submit', async function (e) {
            if (e.target.id === 'ticker-form') {
                e.preventDefault();
                const message = document.getElementById('ticker-message').value.trim();
                const header = document.getElementById('ticker-header').value.trim() || 'FS42';
                const style = document.getElementById('ticker-style').value;
                const iterations = parseInt(document.getElementById('ticker-iterations').value) || 2;
                if (!message) {
                    alert('Please enter a ticker message');
                    return;
                }
                try {
                    const resp = await window.fs42Api.post('api.player.show_ticker', {
                        message: message,
                        header: header,
                        style: style,
                        iterations: iterations
                    });
                    if (resp.status === 'success') {
                        // Clear the form
                        document.getElementById('ticker-message').value = '';
                        document.getElementById('ticker-header').value = 'FS42';
                        document.getElementById('ticker-style').value = 'fieldstation';
                        document.getElementById('ticker-iterations').value = '2';

                        // Show success message briefly
                        const button = e.target.querySelector('button[type="submit"]');
                        const original_text = button.textContent;
                        button.textContent = 'Ticker Sent!';
                        button.disabled = true;
                        setTimeout(function () {
                            button.textContent = original_text;
                            button.disabled = false;
                        }, 2000);
                    }
                }
                catch (error) {
                    alert('Failed to send ticker: ' + error.message);
                }
            }
        });
    };
    Object.assign(self, {
        loadStationSummary, checkQueueConnection, updateStationSummary
    });
    return self;
})();
