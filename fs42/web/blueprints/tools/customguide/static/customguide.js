/*
This Source Code Form is subject to the Mozilla Public License, v. 2.0.
See https://mozilla.org/MPL/2.0/.
*/
window.app = window.app || {};
app.tools = app.tools || {};
app.tools.customguide = (function () {
    let self = {};
    /**
     * Initialize listings and navigation for the current-channel guide
     */
    self.setup = function () {
        const params = new URLSearchParams(window.location.search);
        // The guide shows three full half-hour columns plus part of a fourth.
        const SLOT_COUNT = parseInt(params.get('slots')) || 4;
        const USE_META = params.get('use_meta') !== '0';
        let stations = [];

        // Track the position of the selected channel row
        let selected_row_offset = 0;

        // interactive grid state
        let interactive_row_index = 0;
        let interactive_program_index = 0;
        let interactive_slot_offset = 0;
        let interactive_key_busy = false;
        let guide_toast_timer = null;

        /**
         * Read a guide display setting from the page stylesheet
         */
        function getCSSVar(name) {
            return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
        }

        // Compact guide-clock formats used by the early-2000s cable UI.
        /**
         * Format the guide clock or a half-hour heading with a compact AM/PM suffix
         */
        function formatTime(date, short_suffix = false) {
            const parts = date
                .toLocaleTimeString('en-US', {
                    hour: 'numeric',
                    minute: '2-digit',
                    hour12: true
                })
                .replace(' ', '')
                .toLowerCase();
            if (!short_suffix) {
                return parts;
            }
            return parts.replace('am', 'a').replace('pm', 'p');
        }
        /**
         * Format a selected program's start and end times for the details panel
         */
        function formatProgramTime(start_ms, end_ms) {
            const start = new Date(Number(start_ms));
            const end = new Date(Number(end_ms));
            const start_hour = start.getHours() % 12 || 12;
            const start_minutes = start.getMinutes();
            const start_text =
                start_minutes === 0
                    ? '' + start_hour
                    : '' + start_hour + ':' + String(start_minutes).padStart(2, '0');
            const end_minutes = end.getMinutes();
            const end_hour = end.getHours() % 12 || 12;
            const end_suffix = end.getHours() >= 12 ? 'p' : 'a';
            const end_text =
                end_minutes === 0
                    ? '' + end_hour + end_suffix
                    : '' + end_hour + ':' + String(end_minutes).padStart(2, '0') + end_suffix;
            return '' + start_text + '-' + end_text;
        }
        /**
         * Format local schedule boundaries without converting them to UTC
         */
        function formatDateForAPI(date) {
            const y = date.getFullYear();
            const mo = String(date.getMonth() + 1).padStart(2, '0');
            const d = String(date.getDate()).padStart(2, '0');
            const h = String(date.getHours()).padStart(2, '0');
            const mi = String(date.getMinutes()).padStart(2, '0');
            const s = String(date.getSeconds()).padStart(2, '0');
            return '' + y + '-' + mo + '-' + d + 'T' + h + ':' + mi + ':' + s;
        }

        /**
         * Build half-hour columns for the current or selected time window
         */
        function computeSlotTimes(offset_slots = 0) {
            const now = new Date();
            const base = new Date(
                now.getFullYear(),
                now.getMonth(),
                now.getDate(),
                now.getHours(),
                Math.floor(now.getMinutes() / 30) * 30,
                0,
                0
            );
            base.setMinutes(base.getMinutes() + offset_slots * 30);
            const slots = [];
            for (let i = 0; i < SLOT_COUNT; i++) {
                const start = new Date(base.getTime() + i * 30 * 60 * 1000);
                slots.push({
                    start,
                    end: new Date(start.getTime() + 30 * 60 * 1000)
                });
            }
            return slots;
        }

        /**
         * Load visible stations from the channel API
         */
        async function fetchStations() {
            const all = await window.fs42Common.fetchChannels();
            stations = all.filter(function (s) {
                return !s.hidden;
            });
        }
        /**
         * Fetch programs and optional metadata overlapping the visible time window
         */
        async function fetchAllSchedules(slots, include_meta) {
            if (!stations.length) {
                return {};
            }
            const overall_start = slots[0].start;
            const overall_end = slots[slots.length - 1].end;
            try {
                return await window.fs42Common.fetchGuideSchedules(
                    formatDateForAPI(overall_start),
                    formatDateForAPI(overall_end),
                    include_meta
                );
            }
            catch (e) {
                console.error('error fetching schedules', e);
                return {};
            }
        }

        // Build the channel grid

        /**
         * Replace time headings while preserving the channel-column controls
         */
        function updateGridHeader(slots) {
            const header = document.getElementById('grid-header');
            if (!header) {
                return;
            }
            // Remove old slot labels, keep the channel stub
            const stub = header.querySelector('.grid-channel-stub');
            header.innerHTML = '';
            if (stub) {
                header.appendChild(stub);
            }
            else {
                const new_stub = document.createElement('div');
                new_stub.className = 'grid-channel-stub';
                header.appendChild(new_stub);
            }
            for (const slot of slots) {
                const slot_el = document.createElement('div');
                slot_el.className = 'grid-time-slot';
                slot_el.textContent = formatTime(slot.start, true);
                header.appendChild(slot_el);
            }
        }
        /**
         * Map external program metadata to a supported guide color category
         */
        function getProgramCategory(block, station) {
            const meta = block && block.meta ? block.meta : {};

            // The guide supports only these category class names. External EPG sources
            // may return arbitrary values such as "Game show", "TV series", etc., so
            // never use guide_category directly as a DOM class token.
            const text = [
                meta.guide_category,
                block && block.title,
                meta.title,
                meta.type,
                meta.genre,
                Array.isArray(meta.genres) ? meta.genres.join(' ') : meta.genres,
                station && station.network_name
            ]
                .filter(Boolean)
                .join(' ')
                .toLowerCase();
            if (
                /(sports|football|basketball|baseball|hockey|soccer|golf|tennis|espn|fox sports|nhl|nba|nfl|mlb)/.test(
                    text
                )
            ) {
                return 'sports';
            }
            if (/(movie|film|feature|cinema)/.test(text)) {
                return 'movie';
            }
            if (/(kids|children|cartoon|animation|nick|nik|toons|disney|spongebob|zoey|fairly)/.test(text)) {
                return 'kids';
            }
            return 'default';
        }
        /**
         * Clip a program to the visible time window and attach its selection metadata
         */
        function createGridProgramBlock(block, guide_start_ms, guide_end_ms, total_ms, now, station) {
            const b_start = new Date(block.start_time);
            const b_end = new Date(block.end_time);
            if (b_end.getTime() <= guide_start_ms || b_start.getTime() >= guide_end_ms) {
                return null;
            }
            const vis_start = Math.max(b_start.getTime(), guide_start_ms);
            const vis_end = Math.min(b_end.getTime(), guide_end_ms);
            const left_pct = ((vis_start - guide_start_ms) / total_ms) * 100;
            const width_pct = ((vis_end - vis_start) / total_ms) * 100;
            const el = document.createElement('div');
            el.className = 'grid-program-block';
            el.dataset.startMs = String(b_start.getTime());
            el.dataset.endMs = String(b_end.getTime());
            el.dataset.title = block.title || 'Untitled';
            const meta = USE_META && block.meta;
            const description = (meta && (meta.plot || meta.description)) || block.description || '';
            const rating = (meta && (meta.rating || meta.content_rating)) || '';
            const category = getProgramCategory(block, station);
            el.dataset.description = description;
            el.dataset.rating = typeof rating === 'string' ? rating : '';
            el.dataset.category = category;
            el.classList.add('program-category-' + category);
            if (b_start <= now && b_end > now) {
                el.classList.add('current');
            }
            el.style.left = left_pct + '%';
            el.style.width = 'calc(' + width_pct + '% - 2px)';
            const title_span = document.createElement('span');
            title_span.className = 'program-title';
            title_span.textContent = block.title || 'Untitled';
            el.appendChild(title_span);
            return el;
        }
        /**
         * Create channel rows and their positioned programs, including missing-listing placeholders
         */
        function buildGridStrip(slots, schedules) {
            const strip = document.createElement('div');
            strip.id = 'guide-rows';
            const guide_start_ms = slots[0].start.getTime();
            const guide_end_ms = slots[slots.length - 1].end.getTime();
            const total_ms = guide_end_ms - guide_start_ms;
            const now = new Date();
            const offair_text = getCSSVar('--offair-text').replace(/^["']|["']$/g, '') || 'No Info';
            for (let station_index = 0; station_index < stations.length; station_index++) {
                const station = stations[station_index];
                const row = document.createElement('div');
                row.className = 'grid-row';
                row.dataset.stationIndex = String(station_index);
                row.dataset.channelNumber = String(station.channel_number ?? '');
                row.dataset.channelName = String(station.network_name || '');
                row.dataset.channelLongName = String(station.network_long_name || station.network_name || '');
                const channel_div = document.createElement('div');
                channel_div.className = 'grid-channel';
                const num_span = document.createElement('span');
                num_span.className = 'channel-number';
                num_span.textContent = station.channel_number || '?';
                const name_span = document.createElement('span');
                name_span.className = 'channel-name';
                name_span.textContent = station.network_name;
                channel_div.appendChild(num_span);
                channel_div.appendChild(name_span);
                row.appendChild(channel_div);
                const programs_div = document.createElement('div');
                programs_div.className = 'grid-programs';
                const blocks = schedules[station.network_name] || [];
                if (!station.has_schedule || !blocks.length) {
                    const no_info = document.createElement('div');
                    no_info.className = 'grid-program-block';
                    no_info.dataset.startMs = String(guide_start_ms);
                    no_info.dataset.endMs = String(guide_end_ms);
                    no_info.dataset.title = station.network_long_name || offair_text;
                    no_info.dataset.description = '';
                    no_info.dataset.rating = '';
                    no_info.dataset.category = 'default';
                    no_info.classList.add('program-category-default');
                    no_info.style.left = '0';
                    no_info.style.width = '100%';
                    const t = document.createElement('span');
                    t.className = 'program-title';
                    t.textContent = station.network_long_name || offair_text;
                    no_info.appendChild(t);
                    programs_div.appendChild(no_info);
                }
                else {
                    for (const block of blocks) {
                        const block_el = createGridProgramBlock(
                            block,
                            guide_start_ms,
                            guide_end_ms,
                            total_ms,
                            now,
                            station
                        );
                        if (block_el) {
                            programs_div.appendChild(block_el);
                        }
                    }
                }
                row.appendChild(programs_div);
                strip.appendChild(row);
            }
            return strip;
        }
        /**
         * Refresh the visible time headings and program rows
         */
        async function buildGrid() {
            const slots = computeSlotTimes(interactive_slot_offset);
            updateGridHeader(slots);
            const schedules = await fetchAllSchedules(slots, USE_META);
            const grid_listings = document.getElementById('grid-listings');
            grid_listings.innerHTML = '';
            grid_listings.appendChild(buildGridStrip(slots, schedules));
        }

        /**
         * Return the channel rows available for selection
         */
        function getInteractiveRows() {
            return Array.from(document.querySelectorAll('#guide-rows .grid-row'));
        }
        /**
         * Return program blocks in airtime order for a channel
         */
        function getProgramsForRow(row) {
            if (!row) {
                return [];
            }
            return Array.from(row.querySelectorAll('.grid-program-block'));
        }
        /**
         * Find the midpoint of a program for navigation between channels
         */
        function getProgramCenterMs(program) {
            const start = Number(program?.dataset.startMs);
            const end = Number(program?.dataset.endMs);
            if (Number.isFinite(start) && Number.isFinite(end)) {
                return start + (end - start) / 2;
            }
            return Date.now();
        }
        /**
         * Find the program nearest the requested airtime
         */
        function findClosestProgramIndex(programs, target_ms) {
            if (!programs.length) {
                return 0;
            }
            let best_index = 0;
            let best_distance = Infinity;
            programs.forEach(function (program, index) {
                const start = Number(program.dataset.startMs);
                const end = Number(program.dataset.endMs);
                if (Number.isFinite(start) && Number.isFinite(end) && target_ms >= start && target_ms < end) {
                    best_index = index;
                    best_distance = -1;
                    return;
                }
                if (best_distance < 0) {
                    return;
                }
                const distance = Math.abs(getProgramCenterMs(program) - target_ms);
                if (distance < best_distance) {
                    best_distance = distance;
                    best_index = index;
                }
            });
            return best_index;
        }
        /**
         * Show temporary tuning feedback or an error message
         */
        function showGuideToast(message, is_error = false) {
            let toast = document.getElementById('guide-action-toast');
            if (!toast) {
                toast = document.createElement('div');
                toast.id = 'guide-action-toast';
                toast.setAttribute('aria-live', 'polite');
                document.body.appendChild(toast);
            }
            toast.textContent = message;
            toast.classList.toggle('error', is_error);
            toast.classList.add('visible');
            if (guide_toast_timer) {
                clearTimeout(guide_toast_timer);
            }
            guide_toast_timer = setTimeout(function () {
                toast.classList.remove('visible');
            }, 1400);
        }
        /**
         * Scroll the selected channel row into the visible grid
         */
        function ensureInteractiveSelectionVisible() {
            const rows = getInteractiveRows();
            const row = rows[interactive_row_index];
            const listings = document.getElementById('grid-listings');
            const strip = document.getElementById('guide-rows');
            if (!row || !listings || !strip) {
                return;
            }
            const row_top = row.offsetTop;
            const row_bottom = row_top + row.offsetHeight;
            const viewport_height = listings.clientHeight;
            if (row_top < selected_row_offset) {
                selected_row_offset = row_top;
            }
            else if (row_bottom > selected_row_offset + viewport_height) {
                selected_row_offset = row_bottom - viewport_height;
            }
            const max_scroll = Math.max(0, strip.scrollHeight - viewport_height);
            selected_row_offset = Math.max(0, Math.min(selected_row_offset, max_scroll));
            strip.style.transform = 'translateY(-' + selected_row_offset + 'px)';
        }
        /**
         * Fill the details panel from the selected channel and program
         */
        function updateSelectedProgramInfo() {

            const rows = getInteractiveRows();
            const row = rows[interactive_row_index];
            if (!row) {
                return;
            }
            const programs = getProgramsForRow(row);
            const program = programs[interactive_program_index];
            if (!program) {
                return;
            }
            const title_el = document.getElementById('selected-program-title');
            const channel_el = document.getElementById('selected-channel-label');
            const time_el = document.getElementById('selected-program-time');
            const desc_el = document.getElementById('selected-program-description');
            const rating_el = document.getElementById('selected-program-rating');
            if (title_el) {
                title_el.textContent = program.dataset.title || 'No Info';
            }
            if (channel_el) {
                const channel_num = row.dataset.channelNumber || '';
                const channel_name = row.dataset.channelName || '';
                channel_el.textContent = ('' + channel_num + ' ' + channel_name).trim();
            }
            if (time_el) {
                time_el.textContent = formatProgramTime(program.dataset.startMs, program.dataset.endMs);
            }
            if (desc_el) {
                desc_el.textContent =
                    program.dataset.description ||
                    'More information about ' + (program.dataset.title || 'this program') + ' is not available.';
            }
            if (rating_el) {
                rating_el.textContent = program.dataset.rating || 'TV Y';
            }
        }
        /**
         * Highlight the selected program and refresh its details
         */
        function applyInteractiveSelection() {
            const rows = getInteractiveRows();
            if (!rows.length) {
                return;
            }
            interactive_row_index = Math.max(0, Math.min(interactive_row_index, rows.length - 1));
            document.querySelectorAll('.grid-row.guide-selected-row').forEach(function (el) {
                return el.classList.remove('guide-selected-row');
            });
            document.querySelectorAll('.grid-program-block.guide-selected').forEach(function (el) {
                el.classList.remove('guide-selected');
                el.removeAttribute('aria-selected');
            });
            const row = rows[interactive_row_index];
            const programs = getProgramsForRow(row);
            if (!programs.length) {
                return;
            }
            interactive_program_index = Math.max(0, Math.min(interactive_program_index, programs.length - 1));
            row.classList.add('guide-selected-row');
            const program = programs[interactive_program_index];
            program.classList.add('guide-selected');
            program.setAttribute('aria-selected', 'true');
            ensureInteractiveSelectionVisible();
            updateSelectedProgramInfo();
        }
        /**
         * Select a channel and its program nearest the requested airtime
         */
        function selectInteractiveRow(row_index, target_ms) {
            const rows = getInteractiveRows();
            if (!rows.length) {
                return;
            }
            interactive_row_index = Math.max(0, Math.min(row_index, rows.length - 1));
            const programs = getProgramsForRow(rows[interactive_row_index]);
            interactive_program_index = findClosestProgramIndex(programs, target_ms);
            applyInteractiveSelection();
        }
        /**
         * Move the visible schedule window and restore selection around the requested airtime
         */
        async function shiftInteractiveWindow(delta, target_ms) {
            const next_offset = Math.max(0, interactive_slot_offset + delta);
            if (next_offset === interactive_slot_offset) {
                showGuideToast('LIVE');
                return;
            }
            interactive_slot_offset = next_offset;
            const current_row = interactive_row_index;
            await buildGrid();
            const rows = getInteractiveRows();
            const row = rows[Math.max(0, Math.min(current_row, rows.length - 1))];
            const programs = getProgramsForRow(row);
            interactive_row_index = Math.max(0, Math.min(current_row, rows.length - 1));
            interactive_program_index = findClosestProgramIndex(programs, target_ms);
            applyInteractiveSelection();
        }
        /**
         * Select an adjacent program, loading another time window when needed
         */
        async function moveInteractiveHorizontal(direction) {
            const rows = getInteractiveRows();
            const row = rows[interactive_row_index];
            const programs = getProgramsForRow(row);
            if (!programs.length) {
                return;
            }
            const next_index = interactive_program_index + direction;
            if (next_index >= 0 && next_index < programs.length) {
                interactive_program_index = next_index;
                applyInteractiveSelection();
                return;
            }
            const current = programs[interactive_program_index];
            const start = Number(current?.dataset.startMs) || Date.now();
            const end = Number(current?.dataset.endMs) || Date.now();
            const target_ms = direction > 0 ? end + 1 : start - 1;
            await shiftInteractiveWindow(direction, target_ms);
        }
        /**
         * Select an adjacent channel while retaining the current airtime
         */
        function moveInteractiveVertical(direction) {
            const rows = getInteractiveRows();
            if (!rows.length) {
                return;
            }
            const current_programs = getProgramsForRow(rows[interactive_row_index]);
            const current_program = current_programs[interactive_program_index];
            if (!current_program) {
                return;
            }
            const program_start_ms = Number(current_program.dataset.startMs);

            // The leftmost visible grid slot is the start of the current guide window.
            const slots = computeSlotTimes(interactive_slot_offset);
            const leftmost_grid_time_ms = slots[0].start.getTime();

            // Normally preserve the selected program's actual start time.
            // If that start is off-screen to the left, use the visible guide's
            // left edge instead.
            const target_ms = Number.isFinite(program_start_ms)
                ? Math.max(program_start_ms, leftmost_grid_time_ms)
                : leftmost_grid_time_ms;
            selectInteractiveRow(interactive_row_index + direction, target_ms);
        }
        /**
         * Tune the selected channel and report a failed request
         */
        async function tuneInteractiveSelection() {
            const rows = getInteractiveRows();
            const row = rows[interactive_row_index];
            if (!row) {
                return;
            }
            const channel_number = row.dataset.channelNumber;
            if (!channel_number) {
                showGuideToast('NO CHANNEL', true);
                return;
            }

            try {
                await window.fs42Api.get('player/channels/' + encodeURIComponent(channel_number));
            }
            catch (e) {
                console.error('interactive guide tune failed', e);
                showGuideToast('TUNE FAILED', true);
            }
        }
        /**
         * Translate guide navigation keys into selection, time-window, and tuning actions
         */
        async function handleInteractiveKeydown(event) {
            if (interactive_key_busy) {
                return;
            }
            let action = null;
            if (event.key === 'ArrowUp' || event.key === 'PageUp') {
                action = 'up';
            }
            else if (event.key === 'ArrowDown' || event.key === 'PageDown') {
                action = 'down';
            }
            else if (event.key === 'ArrowLeft') {
                action = 'left';
            }
            else if (event.key === 'ArrowRight') {
                action = 'right';
            }
            else if (event.key === 'Enter') {
                action = 'enter';
            }
            else if (event.key === 'Home') {
                action = 'home';
            }
            if (!action) {
                return;
            }
            event.preventDefault();
            event.stopPropagation();
            interactive_key_busy = true;
            try {
                if (action === 'up') {
                    moveInteractiveVertical(-1);
                }
                else if (action === 'down') {
                    moveInteractiveVertical(1);
                }
                else if (action === 'left') {
                    await moveInteractiveHorizontal(-1);
                }
                else if (action === 'right') {
                    await moveInteractiveHorizontal(1);
                }
                else if (action === 'enter') {
                    await tuneInteractiveSelection();
                }
                else if (action === 'home') {
                    interactive_slot_offset = 0;
                    await buildGrid();
                    const rows = getInteractiveRows();
                    const programs = getProgramsForRow(rows[interactive_row_index]);
                    interactive_program_index = findClosestProgramIndex(programs, Date.now());
                    applyInteractiveSelection();
                    showGuideToast('LIVE');
                }
            }
            finally {
                interactive_key_busy = false;
            }
        }
        /**
         * Enable keyboard and pointer selection and select an initial program
         */
        function initGridInteraction() {
            selected_row_offset = 0;
            const rows = getInteractiveRows();
            if (rows.length) {
                interactive_row_index = 0;
                const programs = getProgramsForRow(rows[interactive_row_index]);
                const current_index = programs.findIndex(function (program) {
                    return program.classList.contains('current');
                });
                interactive_program_index =
                    current_index >= 0 ? current_index : findClosestProgramIndex(programs, Date.now());
                applyInteractiveSelection();
            }
            document.addEventListener('keydown', handleInteractiveKeydown);
            const listings = document.getElementById('grid-listings');
            listings.addEventListener('click', function (event) {
                const program = event.target.closest('.grid-program-block');
                const row = event.target.closest('.grid-row');
                if (!program || !row) {
                    return;
                }
                const rows_now = getInteractiveRows();
                interactive_row_index = rows_now.indexOf(row);
                interactive_program_index = getProgramsForRow(row).indexOf(program);
                applyInteractiveSelection();
            });
        }
        /**
         * Load current listings and enable channel and program selection
         */
        async function initGuide() {
            startClock();
            await fetchStations();
            await buildGrid();
            initGridInteraction();
        }

        /**
         * Refresh the guide clock once per second
         */
        function startClock() {
            const el = document.getElementById('clock');
            if (!el) {
                return;
            }
            const tick = function () {
                el.textContent = formatTime(new Date(), false);
            };
            tick();
            setInterval(tick, 1000);
        }

        window.addEventListener('fs42-guide-show', function () {

            // The guide process stays alive between opens. Refresh the visible grid after
            // the already-rendered window is shown so opening is not blocked on API work.
            Promise.resolve()
                .then(fetchStations)
                .then(buildGrid)
                .then(function () {
                    const rows = getInteractiveRows();
                    if (!rows.length) {
                        return;
                    }
                    interactive_row_index = Math.min(interactive_row_index, rows.length - 1);
                    const programs = getProgramsForRow(rows[interactive_row_index]);
                    const current_index = programs.findIndex(function (program) {
                        return program.classList.contains('current');
                    });
                    interactive_program_index =
                        current_index >= 0 ? current_index : findClosestProgramIndex(programs, Date.now());
                    applyInteractiveSelection();
                })
                .catch(function (e) {
                    console.warn('guide refresh after show failed:', e.message);
                });
        });
        document.addEventListener('DOMContentLoaded', initGuide);
    };
    return self;
})();
