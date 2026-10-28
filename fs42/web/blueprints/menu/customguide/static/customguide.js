/*
This Source Code Form is subject to the Mozilla Public License, v. 2.0.
See https://mozilla.org/MPL/2.0/.
*/
window.app = window.app || {};
app.menu = app.menu || {};
app.menu.customguide = (function () {
    let self = {};

    const params = new URLSearchParams(window.location.search);
    const SLOT_COUNT = parseInt(params.get('slots')) || 4;
    const USE_META = params.get('use_meta') !== '0';
    let stations = [];
    let selected_row_offset = 0;
    let interactive_row_index = 0;
    let interactive_program_index = 0;
    let interactive_slot_offset = 0;
    let interactive_key_busy = false;
    let guide_toast_timer = null;

    /**
     * Read a guide display setting from the page stylesheet
     */
    self.getCSSVar = function(name) {
        return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    };
    /**
     * Format a half-hour heading with a compact AM/PM suffix
     */
    self.formatTime = function(date, short_suffix = false) {
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
    };
    /**
     * Format a selected program's start and end times for the details panel
     */
    self.formatProgramTime = function(start_ms, end_ms) {
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
    };
    /**
     * Format local schedule boundaries without converting them to UTC
     */
    self.formatDateForAPI = function(date) {
        const y = date.getFullYear();
        const mo = String(date.getMonth() + 1).padStart(2, '0');
        const d = String(date.getDate()).padStart(2, '0');
        const h = String(date.getHours()).padStart(2, '0');
        const mi = String(date.getMinutes()).padStart(2, '0');
        const s = String(date.getSeconds()).padStart(2, '0');
        return '' + y + '-' + mo + '-' + d + 'T' + h + ':' + mi + ':' + s;
    };
    /**
     * Build half-hour columns for the current or selected time window
     */
    self.computeSlotTimes = function(offset_slots = 0) {
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
    };
    /**
     * Load visible stations from the channel API
     */
    self.fetchStations = async function() {
        const all = await fetchChannels();
        stations = all.filter(function (s) {
            return !s.hidden;
        });
    };
    /**
     * Fetch programs and optional metadata overlapping the visible time window
     */
    self.fetchAllSchedules = async function(slots, include_meta) {
        if (!stations.length) {
            return {};
        }
        const overall_start = slots[0].start;
        const overall_end = slots[slots.length - 1].end;
        try {
            return await fetchGuideSchedules(
                self.formatDateForAPI(overall_start),
                self.formatDateForAPI(overall_end),
                include_meta
            );
        }
        catch (e) {
            console.error('error fetching schedules', e);
            return {};
        }
    };
    /**
     * Replace time headings while preserving the channel-column controls
     */
    self.updateGridHeader = function(slots) {
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
            slot_el.textContent = self.formatTime(slot.start, true);
            header.appendChild(slot_el);
        }
    };
    /**
     * Map external program metadata to a supported guide color category
     */
    self.getProgramCategory = function(block, station) {
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
    };
    /**
     * Clip a program to the visible time window and attach its selection metadata
     */
    self.createGridProgramBlock = function(block, guide_start_ms, guide_end_ms, total_ms, now, station) {
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
        const category = self.getProgramCategory(block, station);
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
    };
    /**
     * Create channel rows and their positioned programs, including missing-listing placeholders
     */
    self.buildGridStrip = function(slots, schedules) {
        const strip = document.createElement('div');
        strip.id = 'guide-rows';
        const guide_start_ms = slots[0].start.getTime();
        const guide_end_ms = slots[slots.length - 1].end.getTime();
        const total_ms = guide_end_ms - guide_start_ms;
        const now = new Date();
        const offair_text = self.getCSSVar('--offair-text').replace(/^["']|["']$/g, '') || 'No Info';
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
                    const block_el = self.createGridProgramBlock(
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
    };
    /**
     * Refresh the visible time headings and program rows
     */
    self.buildGrid = async function() {
        const slots = self.computeSlotTimes(interactive_slot_offset);
        self.updateGridHeader(slots);
        const schedules = await self.fetchAllSchedules(slots, USE_META);
        const grid_listings = document.getElementById('grid-listings');
        grid_listings.innerHTML = '';
        grid_listings.appendChild(self.buildGridStrip(slots, schedules));
    };
    /**
     * Return the channel rows available for selection
     */
    self.getInteractiveRows = function() {
        return Array.from(document.querySelectorAll('#guide-rows .grid-row'));
    };
    /**
     * Return program blocks in airtime order for a channel
     */
    self.getProgramsForRow = function(row) {
        if (!row) {
            return [];
        }
        return Array.from(row.querySelectorAll('.grid-program-block'));
    };
    /**
     * Find the midpoint of a program for navigation between channels
     */
    self.getProgramCenterMs = function(program) {
        const start = Number(program?.dataset.startMs);
        const end = Number(program?.dataset.endMs);
        if (Number.isFinite(start) && Number.isFinite(end)) {
            return start + (end - start) / 2;
        }
        return Date.now();
    };
    /**
     * Find the program nearest the requested airtime
     */
    self.findClosestProgramIndex = function(programs, target_ms) {
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
            const distance = Math.abs(self.getProgramCenterMs(program) - target_ms);
            if (distance < best_distance) {
                best_distance = distance;
                best_index = index;
            }
        });
        return best_index;
    };
    /**
     * Show temporary tuning feedback or an error message
     */
    self.showGuideToast = function(message, is_error = false) {
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
    };
    /**
     * Scroll the selected channel row into the visible grid
     */
    self.ensureInteractiveSelectionVisible = function() {
        const rows = self.getInteractiveRows();
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
    };
    /**
     * Fill the details panel from the selected channel and program
     */
    self.updateSelectedProgramInfo = function() {

        const rows = self.getInteractiveRows();
        const row = rows[interactive_row_index];
        if (!row) {
            return;
        }
        const programs = self.getProgramsForRow(row);
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
            time_el.textContent = self.formatProgramTime(program.dataset.startMs, program.dataset.endMs);
        }
        if (desc_el) {
            desc_el.textContent =
                program.dataset.description ||
                'More information about ' + (program.dataset.title || 'this program') + ' is not available.';
        }
        if (rating_el) {
            rating_el.textContent = program.dataset.rating || 'TV Y';
        }
    };
    /**
     * Highlight the selected program and refresh its details
     */
    self.applyInteractiveSelection = function() {
        const rows = self.getInteractiveRows();
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
        const programs = self.getProgramsForRow(row);
        if (!programs.length) {
            return;
        }
        interactive_program_index = Math.max(0, Math.min(interactive_program_index, programs.length - 1));
        row.classList.add('guide-selected-row');
        const program = programs[interactive_program_index];
        program.classList.add('guide-selected');
        program.setAttribute('aria-selected', 'true');
        self.ensureInteractiveSelectionVisible();
        self.updateSelectedProgramInfo();
    };
    /**
     * Select a channel and its program nearest the requested airtime
     */
    self.selectInteractiveRow = function(row_index, target_ms) {
        const rows = self.getInteractiveRows();
        if (!rows.length) {
            return;
        }
        interactive_row_index = Math.max(0, Math.min(row_index, rows.length - 1));
        const programs = self.getProgramsForRow(rows[interactive_row_index]);
        interactive_program_index = self.findClosestProgramIndex(programs, target_ms);
        self.applyInteractiveSelection();
    };
    /**
     * Move the visible schedule window and restore selection around the requested airtime
     */
    self.shiftInteractiveWindow = async function(delta, target_ms) {
        const next_offset = Math.max(0, interactive_slot_offset + delta);
        if (next_offset === interactive_slot_offset) {
            self.showGuideToast('LIVE');
            return;
        }
        interactive_slot_offset = next_offset;
        const current_row = interactive_row_index;
        await self.buildGrid();
        const rows = self.getInteractiveRows();
        const row = rows[Math.max(0, Math.min(current_row, rows.length - 1))];
        const programs = self.getProgramsForRow(row);
        interactive_row_index = Math.max(0, Math.min(current_row, rows.length - 1));
        interactive_program_index = self.findClosestProgramIndex(programs, target_ms);
        self.applyInteractiveSelection();
    };
    /**
     * Select an adjacent program, loading another time window when needed
     */
    self.moveInteractiveHorizontal = async function(direction) {
        const rows = self.getInteractiveRows();
        const row = rows[interactive_row_index];
        const programs = self.getProgramsForRow(row);
        if (!programs.length) {
            return;
        }
        const next_index = interactive_program_index + direction;
        if (next_index >= 0 && next_index < programs.length) {
            interactive_program_index = next_index;
            self.applyInteractiveSelection();
            return;
        }
        const current = programs[interactive_program_index];
        const start = Number(current?.dataset.startMs) || Date.now();
        const end = Number(current?.dataset.endMs) || Date.now();
        const target_ms = direction > 0 ? end + 1 : start - 1;
        await self.shiftInteractiveWindow(direction, target_ms);
    };
    /**
     * Select an adjacent channel while retaining the current airtime
     */
    self.moveInteractiveVertical = function(direction) {
        const rows = self.getInteractiveRows();
        if (!rows.length) {
            return;
        }
        const current_programs = self.getProgramsForRow(rows[interactive_row_index]);
        const current_program = current_programs[interactive_program_index];
        if (!current_program) {
            return;
        }
        const program_start_ms = Number(current_program.dataset.startMs);

        // The leftmost visible grid slot is the start of the current guide window.
        const slots = self.computeSlotTimes(interactive_slot_offset);
        const leftmost_grid_time_ms = slots[0].start.getTime();

        // Normally preserve the selected program's actual start time.
        // If that start is off-screen to the left, use the visible guide's
        // left edge instead.
        const target_ms = Number.isFinite(program_start_ms)
            ? Math.max(program_start_ms, leftmost_grid_time_ms)
            : leftmost_grid_time_ms;
        self.selectInteractiveRow(interactive_row_index + direction, target_ms);
    };
    /**
     * Tune the selected channel and report a failed request
     */
    self.tuneInteractiveSelection = async function() {
        const rows = self.getInteractiveRows();
        const row = rows[interactive_row_index];
        if (!row) {
            return;
        }
        const channel_number = row.dataset.channelNumber;
        if (!channel_number) {
            self.showGuideToast('NO CHANNEL', true);
            return;
        }

        try {
            await apiGet('player/channels/' + encodeURIComponent(channel_number));
        }
        catch (e) {
            console.error('interactive guide tune failed', e);
            self.showGuideToast('TUNE FAILED', true);
        }
    };
    /**
     * Translate guide navigation keys into selection, time-window, and tuning actions
     */
    self.handleInteractiveKeydown = async function(event) {
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
                self.moveInteractiveVertical(-1);
            }
            else if (action === 'down') {
                self.moveInteractiveVertical(1);
            }
            else if (action === 'left') {
                await self.moveInteractiveHorizontal(-1);
            }
            else if (action === 'right') {
                await self.moveInteractiveHorizontal(1);
            }
            else if (action === 'enter') {
                await self.tuneInteractiveSelection();
            }
            else if (action === 'home') {
                interactive_slot_offset = 0;
                await self.buildGrid();
                const rows = self.getInteractiveRows();
                const programs = self.getProgramsForRow(rows[interactive_row_index]);
                interactive_program_index = self.findClosestProgramIndex(programs, Date.now());
                self.applyInteractiveSelection();
                self.showGuideToast('LIVE');
            }
        }
        finally {
            interactive_key_busy = false;
        }
    };
    /**
     * Enable keyboard and pointer selection and select an initial program
     */
    self.initGridInteraction = function() {
        selected_row_offset = 0;
        const rows = self.getInteractiveRows();
        if (rows.length) {
            interactive_row_index = 0;
            const programs = self.getProgramsForRow(rows[interactive_row_index]);
            const current_index = programs.findIndex(function (program) {
                return program.classList.contains('current');
            });
            interactive_program_index =
                current_index >= 0 ? current_index : self.findClosestProgramIndex(programs, Date.now());
            self.applyInteractiveSelection();
        }
        document.addEventListener('keydown', self.handleInteractiveKeydown);
        const listings = document.getElementById('grid-listings');
        listings.addEventListener('click', function (event) {
            const program = event.target.closest('.grid-program-block');
            const row = event.target.closest('.grid-row');
            if (!program || !row) {
                return;
            }
            const rows_now = self.getInteractiveRows();
            interactive_row_index = rows_now.indexOf(row);
            interactive_program_index = self.getProgramsForRow(row).indexOf(program);
            self.applyInteractiveSelection();
        });
    };
    /**
     * Load current listings and enable channel and program selection
     */
    self.initGuide = async function() {
        await self.fetchStations();
        await self.buildGrid();
        self.initGridInteraction();
    };

    /** Initialize the page and bind its controls. */
    /** Handle fs42-guide-show. */
    self.onFs42GuideShow = function() {

        // The guide process stays alive between opens. Refresh the visible grid after
        // the already-rendered window is shown so opening is not blocked on API work.
        Promise.resolve()
            .then(self.fetchStations)
            .then(self.buildGrid)
            .then(function () {
                const rows = self.getInteractiveRows();
                if (!rows.length) {
                    return;
                }
                interactive_row_index = Math.min(interactive_row_index, rows.length - 1);
                const programs = self.getProgramsForRow(rows[interactive_row_index]);
                const current_index = programs.findIndex(function (program) {
                    return program.classList.contains('current');
                });
                interactive_program_index =
                    current_index >= 0 ? current_index : self.findClosestProgramIndex(programs, Date.now());
                self.applyInteractiveSelection();
            })
            .catch(function (e) {
                console.warn('guide refresh after show failed:', e.message);
            });
    };

    self.setup = function() {
        window.addEventListener('fs42-guide-show', self.onFs42GuideShow);
        return self.initGuide();
    };
    return self;
})();
