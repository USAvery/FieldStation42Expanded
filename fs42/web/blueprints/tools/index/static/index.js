/*
This Source Code Form is subject to the Mozilla Public License, v. 2.0.
See https://mozilla.org/MPL/2.0/.
*/
window.app = window.app || {};
app.tools = app.tools || {};
app.tools.index = (function () {
    let self = {};
    /**
     * Set up the index page
     */
    self.setup = function () {
        // Initialize page layout
        document.addEventListener('DOMContentLoaded', async function () {
            window.fs42Common.initTheme();
            const content = [
                '',
                '        <div class="pure-u-1" style="margin-bottom:2em;">',
                '            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1em;">',
                '                <h2 style="margin:0;">On Now</h2>',
                '                <a href="/static/guide.html" class="pure-button pure-button-primary" style="font-size:0.8em;">View Full Guide</a>',
                '            </div>',
                '            <iframe src="/static/guide_frame.html" ',
                '                    style="width:100%; height:200px; border:1px solid #666; border-radius:4px; display:block;"',
                '                    title="Current Programming">',
                '                <p>Your browser does not support iframes. <a href="/static/guide.html">View Guide</a></p>',
                '            </iframe>',
                '        </div>',
                '',
                '        <div id="station-summary" class="pure-u-1">',
                '            <h2>Station Summary</h2>',
                '            <div id="stations-list">',
                '                <p>Loading station data...</p>',
                '            </div>',
                '        </div>',
                '',
                '        <div id="ticker-control" class="pure-u-1" style="display:none; margin-top:1.5em; margin-bottom:1.5em;">',
                '            <h2 style="margin-bottom:1em; font-size:1.2em;">Display Message</h2>',
                '            <form id="ticker-form" class="pure-form pure-form-aligned">',
                '                <fieldset style="padding:1em;">',
                '                    <div class="pure-g" style="align-items:end;">',
                '                        <div class="pure-u-1 pure-u-md-1-3" style="padding-right:0.5em;">',
                '                            <label for="ticker-message" style="margin-top:0;">Message</label>',
                '                            <input id="ticker-message" type="text" class="pure-input-1" placeholder="Enter ticker message..." required>',
                '                        </div>',
                '                        <div class="pure-u-1 pure-u-md-1-6" style="padding:0 0.25em;">',
                '                            <label for="ticker-header">Header</label>',
                '                            <input id="ticker-header" type="text" class="pure-input-1" value="FS42" placeholder="Header">',
                '                        </div>',
                '                        <div class="pure-u-1 pure-u-md-1-4" style="padding:0 0.25em;">',
                '                            <label for="ticker-style">Style</label>',
                '                            <select id="ticker-style" class="pure-input-1">',
                '                                <option value="fieldstation">FieldStation</option>',
                '                                <option value="breaking">Breaking</option>',
                '                                <option value="weather">Weather</option>',
                '                                <option value="sports">Sports</option>',
                '                                <option value="financial">Financial</option>',
                '                                <option value="election">Election</option>',
                '                            </select>',
                '                        </div>',
                '                        <div class="pure-u-1 pure-u-md-1-12" style="padding:0 0.25em;">',
                '                            <label for="ticker-iterations">Count</label>',
                '                            <input id="ticker-iterations" type="number" class="pure-input-1" value="2" min="1" max="10" style="text-align:center;">',
                '                        </div>',
                '                        <div class="pure-u-1 pure-u-md-1-6" style="padding-left:0.5em;">',
                '                            <label style="margin-top:0; visibility:hidden;">Action</label>',
                '                            <button type="submit" class="pure-button pure-button-primary" style="width:100%;">Send</button>',
                '                        </div>',
                '                    </div>',
                '                </fieldset>',
                '            </form>',
                '        </div>',
                '        <div style="text-align:center; margin-top:1em;">',
                '            <span style="font-size:1.5em;font-weight:bold;">FieldStation42</span>',
                '            <span style="margin-left:1em; font-size:1.2em;">It\'s Up To You.</span>',
                '        </div>',
                '    '
            ].join('\n');
            document.body.innerHTML = await window.fs42Common.createPageLayout('', content);
            // Load page data after its controls have been added to the document
            await loadStationSummary();
            await checkQueueConnection();
            setInterval(checkQueueConnection, 5000);
        });

        // Fetch and display summary from /summary API
        /**
         * Load Station Summary
         */
        async function loadStationSummary() {
            try {
                const resp = await window.fs42Api.get('summary');
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
                        name +
                        "</strong></td>\n                <td data-label='Channel'>" +
                        channel +
                        "</td>\n                <td data-label='Catalog Entries'>" +
                        entry_count +
                        "</td>\n                <td data-label='Total Duration'>" +
                        total_duration +
                        "</td>\n                <td data-label='Schedule Start'>" +
                        start +
                        "</td>\n                <td data-label='Schedule End'>" +
                        end +
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

        // Check queue connection status and show/hide ticker controls
        /**
         * Check Queue Connection
         */
        async function checkQueueConnection() {
            try {
                const resp = await window.fs42Api.get('player/status/queue_connected');
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

        // Check queue connection initially and periodically

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
                    const resp = await window.fs42Api.post('player/ticker', {
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
        self.loadStationSummary = loadStationSummary;
        self.checkQueueConnection = checkQueueConnection;
        self.updateStationSummary = updateStationSummary;
    };
    return self;
})();
