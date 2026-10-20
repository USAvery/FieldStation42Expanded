/*
This Source Code Form is subject to the Mozilla Public License, v. 2.0.
See https://mozilla.org/MPL/2.0/.
*/
window.app = window.app || {};
app.tools = app.tools || {};
app.tools.customguide = (function () {
    let self = {};
    /**
     * Set up the customguide page
     */
    self.setup = function () {
        const params = new URLSearchParams(window.location.search);
        const THEME = params.get('theme') || '80s';
        const SLOT_COUNT = parseInt(params.get('slots')) || 3;
        const HEADER_TEXT = params.get('header') || null;
        const PAUSE_OVERRIDE = params.get('pause');
        const MOCK = params.get('mock') === '1';
        const INTERACTIVE = params.get('interactive') === '1';
        const USE_META = params.get('use_meta') !== '0';
        const SHOW_DESCRIPTION = ['1', 'true'].includes((params.get('show_description') || '').toLowerCase());
        const MUSIC_PATH = params.get('music');
        const VIDEOS = params.get('videos') !== 'false';
        const MESSAGES_PATH = params.get('messages');
        const LOOP = params.get('loop') !== '0';
        let RANDOM_START = params.get('random_start') === '1';
        let stations = [];

        // list-mode scroll state
        let anim_frame = null;
        let scroll_y = 0;
        let pause_until = 0;

        // grid-mode scroll state
        let grid_anim_frame = null;
        let grid_scroll_y = 0;
        let grid_pause_until = 0;

        // interactive grid state
        let interactive_row_index = 0;
        let interactive_program_index = 0;
        let interactive_slot_offset = 0;
        let interactive_key_busy = false;
        let guide_toast_timer = null;

        // music
        let music_playlist = [];
        let current_music_index = 0;
        let bg_player = null;

        // video
        let video_playlist = [];
        let current_video_index = 0;
        let bg_video_player = null;

        // text carousel
        let messages = [];
        let message_carousel_timer = null;
        /**
         * Load Theme
         */
        function loadTheme(name) {
            return new Promise(function (resolve) {
                const link = document.createElement('link');
                link.rel = 'stylesheet';
                link.href = 'themes/' + name + '.css';
                link.addEventListener('load', resolve);
                link.addEventListener('error', function () {
                    console.warn('theme "' + name + '" not found, falling back to 80s.');
                    if (name !== '80s') {
                        loadTheme('80s').then(resolve);
                    }
                    else {
                        resolve();
                    }
                });
                document.head.appendChild(link);
            });
        }
        /**
         * Get CSSVar
         */
        function getCSSVar(name) {
            return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
        }
        /**
         * Format Time12
         */
        function formatTime12(date) {
            return date.toLocaleTimeString('en-US', {
                hour: 'numeric',
                minute: '2-digit',
                hour12: true
            });
        }
        /**
         * Format Date For API
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
         * Get Pause Duration
         */
        function getPauseDuration() {
            if (PAUSE_OVERRIDE) {
                return parseFloat(PAUSE_OVERRIDE) * 1000;
            }
            const match = getCSSVar('--scroll-pause').match(/([\d.]+)\s*s/);
            return match ? parseFloat(match[1]) * 1000 : 5000;
        }
        /**
         * Get Scroll Speed
         */
        function getScrollSpeed() {
            const val = parseFloat(getCSSVar('--scroll-speed'));
            return !isNaN(val) && val > 0 ? val : 1.1;
        }
        /**
         * Compute Slot Times
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

        // mock data for local scroll testing (?mock=1)
        const MOCK_SHOWS = [
            'Late Night Movie',
            'The Evening News',
            'Sports Center',
            'Nature Documentary',
            'Sitcom Reruns',
            'Talk Show',
            'Crime Drama',
            'Cooking Hour',
            'Saturday Morning Cartoons',
            'Local Weather Update',
            'Classic Film',
            'Music Videos',
            'Game Show Marathon',
            'Science Fiction Theater',
            'Western Double Feature',
            'Home Shopping',
            'News Magazine',
            "Children's Programming",
            'Live Sports',
            'Comedy Special'
        ];
        /**
         * Mock Fetch Stations
         */
        function mockFetchStations() {
            stations = Array.from(
                {
                    length: 24
                },
                function (_, i) {
                    const num = i + 2;
                    return {
                        channel_number: num,
                        network_name: 'ch' + num,
                        network_long_name: 'Channel ' + num,
                        has_schedule: true
                    };
                }
            );
        }
        /**
         * Mock Fetch All Schedules
         */
        function mockFetchAllSchedules(slots) {
            const schedules = {};
            const slot_ms = 30 * 60 * 1000;
            for (const station of stations) {
                const blocks = [];
                let t = slots[0].start.getTime();
                const end = slots[slots.length - 1].end.getTime();
                while (t < end) {
                    const duration = (Math.floor(Math.random() * 3) + 1) * slot_ms;
                    const title = MOCK_SHOWS[Math.floor(Math.random() * MOCK_SHOWS.length)];
                    blocks.push({
                        start_time: new Date(t).toISOString(),
                        end_time: new Date(t + duration).toISOString(),
                        title
                    });
                    t += duration;
                }
                schedules[station.network_name] = blocks;
            }
            return schedules;
        }
        /**
         * Fetch Stations
         */
        async function fetchStations() {
            const all = await window.fs42Common.fetchChannels();
            stations = all.filter(function (s) {
                return !s.hidden;
            });
        }
        /**
         * Fetch All Schedules
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

        // ===== LIST MODE (80s) =====

        /**
         * Find Block For Slot
         */
        function findBlockForSlot(blocks, slot_start) {
            for (const block of blocks) {
                const b_start = new Date(block.start_time);
                const b_end = new Date(block.end_time);
                if (b_start <= slot_start && b_end > slot_start) {
                    return {
                        block,
                        continued: b_start < slot_start
                    };
                }
            }
            return null;
        }
        /**
         * Build Scroll Strip
         */
        function buildScrollStrip(slots, schedules) {
            const strip = document.createElement('div');
            strip.id = 'guide-scroll-strip';
            const channel_after = getCSSVar('--channel-position').replace(/["']/g, '') === 'after';
            const offair_text = getCSSVar('--offair-text').replace(/^["']|["']$/g, '') || 'Offair';
            for (const slot of slots) {
                const heading = document.createElement('div');
                heading.className = 'time-slot-heading';
                heading.textContent = formatTime12(slot.start);
                strip.appendChild(heading);
                for (const station of stations) {
                    const row = document.createElement('div');
                    row.className = 'listing-row';
                    if (channel_after) {
                        row.classList.add('channel-after');
                    }
                    const channel_info = document.createElement('span');
                    channel_info.className = 'channel-info';
                    const num_span = document.createElement('span');
                    num_span.className = 'channel-number';
                    num_span.textContent = station.channel_number || '?';
                    const name_span = document.createElement('span');
                    name_span.className = 'channel-name';
                    const name = station.network_name;
                    name_span.textContent = name.length > 10 ? name.slice(0, 10) + '…' : name;
                    channel_info.appendChild(num_span);
                    channel_info.appendChild(name_span);
                    const title_span = document.createElement('span');
                    title_span.className = 'show-title';
                    const result = findBlockForSlot(schedules[station.network_name] || [], slot.start);
                    if (result) {
                        const t = result.block.title || offair_text;
                        title_span.textContent = t.length > 20 ? t.slice(0, 20) + '…' : t;
                        if (result.continued) {
                            row.classList.add('continued');
                        }
                    }
                    else {
                        title_span.textContent = offair_text;
                    }
                    row.appendChild(channel_info);
                    row.appendChild(title_span);
                    strip.appendChild(row);
                }
            }
            return strip;
        }
        /**
         * Stop Scrolling
         */
        function stopScrolling() {
            if (anim_frame) {
                cancelAnimationFrame(anim_frame);
                anim_frame = null;
            }
        }
        /**
         * Build Guide
         */
        async function buildGuide() {
            const slots = computeSlotTimes();
            const schedules = MOCK ? mockFetchAllSchedules(slots) : await fetchAllSchedules(slots);
            const listings = document.getElementById('guide-listings');
            listings.innerHTML = '';
            listings.appendChild(buildScrollStrip(slots, schedules));
        }
        /**
         * Start Scrolling
         */
        function startScrolling() {
            stopScrolling();
            const listings = document.getElementById('guide-listings');
            const strip = document.getElementById('guide-scroll-strip');
            if (!strip) {
                return;
            }
            const px_per_ms = getScrollSpeed() / 50;
            const pause_ms = getPauseDuration();
            scroll_y = 0;
            strip.style.transform = 'translateY(0)';
            pause_until = performance.now() + pause_ms;
            let last_time = null;
            /**
             * Tick
             */
            function tick(now) {
                if (now < pause_until) {
                    anim_frame = requestAnimationFrame(tick);
                    return;
                }
                const max_scroll = strip.offsetHeight - listings.clientHeight;
                if (max_scroll <= 0) {
                    setTimeout(async function () {
                        await buildGuide();
                        startScrolling();
                    }, pause_ms);
                    return;
                }
                if (last_time !== null) {
                    scroll_y += px_per_ms * (now - last_time);
                }
                last_time = now;
                if (scroll_y >= max_scroll) {
                    strip.style.transform = 'translateY(-' + max_scroll + 'px)';
                    last_time = null;
                    setTimeout(async function () {
                        await buildGuide();
                        startScrolling();
                    }, pause_ms);
                    return;
                }
                strip.style.transform = 'translateY(-' + scroll_y + 'px)';
                anim_frame = requestAnimationFrame(tick);
            }
            anim_frame = requestAnimationFrame(tick);
        }

        // ===== GRID MODE (90s / 00s) =====

        /**
         * Build Grid DOM
         */
        function buildGridDOM() {
            const listings = document.getElementById('guide-listings');
            listings.classList.add('grid-mode');
            listings.innerHTML = [
                '',
                '    <div id="top-panel">',
                '      <div id="video-panel"><video id="bgVideoPlayer" preload="auto"></video></div>',
                '      <div id="text-panel">',
                '        <div id="text-message-title"></div>',
                '        <div id="text-message-body"></div>',
                '      </div>',
                '    </div>',
                '    <div id="grid-wrapper">',
                '      <div id="grid-header"><div class="grid-channel-stub"><span id="clock"></span></div></div>',
                '      <div id="grid-listings"></div>',
                '    </div>',
                '  '
            ].join('\n');
            const video_side = getCSSVar('--video-side').replace(/["']/g, '') || 'left';
            if (video_side === 'right') {
                document.getElementById('video-panel').style.order = '1';
                document.getElementById('text-panel').style.order = '0';
            }
            bg_video_player = document.getElementById('bgVideoPlayer');
        }
        /**
         * Update Grid Header
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
                slot_el.textContent = formatTime12(slot.start);
                header.appendChild(slot_el);
            }
        }
        /**
         * Create Grid Program Block
         */
        function createGridProgramBlock(block, guide_start_ms, guide_end_ms, total_ms, now) {
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
            if (b_start <= now && b_end > now) {
                el.classList.add('current');
            }
            el.style.left = left_pct + '%';
            el.style.width = 'calc(' + width_pct + '% - 2px)';
            const title_span = document.createElement('span');
            title_span.className = 'program-title';
            title_span.textContent = block.title || 'Untitled';
            el.appendChild(title_span);
            const meta = USE_META && block.meta;
            let desc = meta && meta.plot;
            let is_episode_title = false;
            if (meta && meta.type === 'episode' && !SHOW_DESCRIPTION && meta.title) {
                desc = meta.title;
                is_episode_title = true;
            }
            if (desc) {
                const desc_span = document.createElement('span');
                desc_span.className = is_episode_title ? 'program-desc is-episode-title' : 'program-desc';
                desc_span.textContent = desc;
                el.appendChild(desc_span);
            }
            return el;
        }
        /**
         * Build Grid Strip
         */
        function buildGridStrip(slots, schedules) {
            const strip = document.createElement('div');
            strip.id = 'grid-scroll-strip';
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
                            now
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
         * Build Grid
         */
        async function buildGrid() {
            const slots = computeSlotTimes(INTERACTIVE ? interactive_slot_offset : 0);
            updateGridHeader(slots);
            const schedules = MOCK ? mockFetchAllSchedules(slots) : await fetchAllSchedules(slots, USE_META);
            const grid_listings = document.getElementById('grid-listings');
            grid_listings.innerHTML = '';
            grid_listings.appendChild(buildGridStrip(slots, schedules));
        }
        /**
         * Start Grid Scrolling
         */
        function startGridScrolling() {
            if (grid_anim_frame) {
                cancelAnimationFrame(grid_anim_frame);
                grid_anim_frame = null;
            }
            const listings = document.getElementById('grid-listings');
            const strip = document.getElementById('grid-scroll-strip');
            if (!strip || !listings) {
                return;
            }
            const px_per_ms = getScrollSpeed() / 50;
            const pause_ms = getPauseDuration();

            // Clean up any previous clone
            const existing_clone = document.getElementById('grid-scroll-strip-clone');
            if (existing_clone) {
                existing_clone.remove();
            }
            let clone;
            const original_height = strip.scrollHeight;

            // Loop guide if true.
            if (LOOP) {
                clone = strip.cloneNode(true);
                clone.id = 'grid-scroll-strip-clone';
                clone.setAttribute('aria-hidden', 'true');
                strip.parentElement.appendChild(clone);
                clone.style.transform = 'translateY(' + original_height + 'px)';
            }
            // Random channel start
            if (RANDOM_START) {
                grid_scroll_y = Math.random() * original_height;
                RANDOM_START = false;
            }
            else if (!LOOP) {
                grid_scroll_y = 0;
            }
            strip.style.transform = 'translateY(0)';
            grid_pause_until = LOOP ? 0 : performance.now() + pause_ms;
            let last_time = null;
            /**
             * Tick
             */
            function tick(now) {
                if (now < grid_pause_until) {
                    grid_anim_frame = requestAnimationFrame(tick);
                    return;
                }

                // Loop guide if true.
                if (LOOP) {
                    if (last_time !== null) {
                        grid_scroll_y += px_per_ms * (now - last_time);
                    }
                    last_time = now;
                    if (grid_scroll_y >= original_height) {
                        grid_scroll_y -= original_height;
                        if (grid_anim_frame) {
                            cancelAnimationFrame(grid_anim_frame);
                            grid_anim_frame = null;
                        }
                        buildGrid().then(startGridScrolling);
                        return;
                    }
                    strip.style.transform = 'translateY(-' + grid_scroll_y + 'px)';
                    clone.style.transform = 'translateY(' + (original_height - grid_scroll_y) + 'px)';
                    grid_anim_frame = requestAnimationFrame(tick);
                }
                else {
                    const max_scroll = strip.offsetHeight - listings.clientHeight;
                    if (max_scroll <= 0) {
                        setTimeout(async function () {
                            await buildGrid();
                            startGridScrolling();
                        }, pause_ms);
                        return;
                    }
                    if (last_time !== null) {
                        grid_scroll_y += px_per_ms * (now - last_time);
                    }
                    last_time = now;
                    if (grid_scroll_y >= max_scroll) {
                        strip.style.transform = 'translateY(-' + max_scroll + 'px)';
                        last_time = null;
                        setTimeout(async function () {
                            await buildGrid();
                            startGridScrolling();
                        }, pause_ms);
                        return;
                    }
                    strip.style.transform = 'translateY(-' + grid_scroll_y + 'px)';
                    grid_anim_frame = requestAnimationFrame(tick);
                }
            }
            grid_anim_frame = requestAnimationFrame(tick);
        }
        /**
         * Stop Grid Scrolling For Interaction
         */
        function stopGridScrollingForInteraction() {
            if (grid_anim_frame) {
                cancelAnimationFrame(grid_anim_frame);
                grid_anim_frame = null;
            }
            const clone = document.getElementById('grid-scroll-strip-clone');
            if (clone) {
                clone.remove();
            }
        }
        /**
         * Get Interactive Rows
         */
        function getInteractiveRows() {
            return Array.from(document.querySelectorAll('#grid-scroll-strip .grid-row'));
        }
        /**
         * Get Programs For Row
         */
        function getProgramsForRow(row) {
            if (!row) {
                return [];
            }
            return Array.from(row.querySelectorAll('.grid-program-block'));
        }
        /**
         * Get Program Center Ms
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
         * Find Closest Program Index
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
         * Show Guide Toast
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
         * Ensure Interactive Selection Visible
         */
        function ensureInteractiveSelectionVisible() {
            const rows = getInteractiveRows();
            const row = rows[interactive_row_index];
            const listings = document.getElementById('grid-listings');
            const strip = document.getElementById('grid-scroll-strip');
            if (!row || !listings || !strip) {
                return;
            }
            const row_top = row.offsetTop;
            const row_bottom = row_top + row.offsetHeight;
            const viewport_height = listings.clientHeight;
            if (row_top < grid_scroll_y) {
                grid_scroll_y = row_top;
            }
            else if (row_bottom > grid_scroll_y + viewport_height) {
                grid_scroll_y = row_bottom - viewport_height;
            }
            const max_scroll = Math.max(0, strip.scrollHeight - viewport_height);
            grid_scroll_y = Math.max(0, Math.min(grid_scroll_y, max_scroll));
            strip.style.transform = 'translateY(-' + grid_scroll_y + 'px)';
        }
        /**
         * Apply Interactive Selection
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
        }
        /**
         * Select Interactive Row
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
         * Shift Interactive Window
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
         * Move Interactive Horizontal
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
         * Move Interactive Vertical
         */
        function moveInteractiveVertical(direction) {
            const rows = getInteractiveRows();
            if (!rows.length) {
                return;
            }
            const current_programs = getProgramsForRow(rows[interactive_row_index]);
            const current_program = current_programs[interactive_program_index];
            const target_ms = getProgramCenterMs(current_program);
            selectInteractiveRow(interactive_row_index + direction, target_ms);
        }
        /**
         * Tune Interactive Selection
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
            if (MOCK) {
                showGuideToast('TUNE CH ' + channel_number + ' (MOCK)');
                console.log('Interactive guide mock tune: channel ' + channel_number);
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
         * Handle Interactive Keydown
         */
        async function handleInteractiveKeydown(event) {
            if (!INTERACTIVE || interactive_key_busy) {
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
         * Init Grid Interaction
         */
        function initGridInteraction() {
            stopGridScrollingForInteraction();
            grid_scroll_y = 0;
            document.body.classList.add('guide-interactive');
            const rows = getInteractiveRows();
            if (rows.length) {
                interactive_row_index = 0;
                const programs = getProgramsForRow(rows[0]);
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
         * Init Grid Mode
         */
        async function initGridMode() {
            document.getElementById('guide-header').style.display = 'none';
            const old_clock = document.getElementById('clock');
            if (old_clock) {
                old_clock.remove();
            }
            buildGridDOM();
            startClock();
            const media_loaded = Promise.all([loadMusicPlaylist(), loadVideoPlaylist(), loadMessages()]);
            if (MOCK) {
                mockFetchStations();
            }
            else {
                await fetchStations();
            }
            await buildGrid();
            if (INTERACTIVE) {
                initGridInteraction();
            }
            else {
                startGridScrolling();
            }
            await media_loaded;
            setupMusic();
            setupVideo();
            startTextCarousel();
        }

        // ===== CLOCK =====

        /**
         * Start Clock
         */
        function startClock() {
            const el = document.getElementById('clock');
            const tick = function () {
                el.textContent = formatTime12(new Date());
            };
            tick();
            setInterval(tick, 1000);
        }

        // ===== RANDOM PLAYBACK =====

        /**
         * Random Other Index
         */
        function randomOtherIndex(playlist, current) {
            if (playlist.length <= 1) {
                return 0;
            }
            let next;
            do {
                next = Math.floor(Math.random() * playlist.length);
            } while (next === current);
            return next;
        }

        // ===== MUSIC =====

        /**
         * Load Music Playlist
         */
        async function loadMusicPlaylist() {
            try {
                if (MUSIC_PATH) {
                    const resp = await fetch('/media/list?path=' + encodeURIComponent(MUSIC_PATH));
                    if (!resp.ok) {
                        throw new Error('HTTP ' + resp.status);
                    }
                    const data = await resp.json();
                    music_playlist = data.files || [];
                }
                else {
                    // Only fall back to the bundled json if the theme allows it
                    const autoload = getCSSVar('--music-autoload').replace(/["']/g, '');
                    if (autoload === 'false') {
                        return;
                    }
                    const resp = await fetch('music_playlist.json');
                    if (!resp.ok) {
                        throw new Error('HTTP ' + resp.status);
                    }
                    const data = await resp.json();
                    music_playlist = data.music_files || [];
                }
            }
            catch (e) {
                console.warn('no music playlist:', e.message);
            }
        }
        /**
         * Play Music Track
         */
        function playMusicTrack(index) {
            if (!bg_player || !music_playlist.length) {
                return;
            }
            current_music_index = index % music_playlist.length;
            bg_player.src = music_playlist[current_music_index];
            bg_player.play().catch(function () {
                document.addEventListener(
                    'click',
                    function () {
                        return bg_player.play();
                    },
                    {
                        once: true
                    }
                );
            });
        }
        /**
         * Setup Music
         */
        function setupMusic() {
            bg_player = document.getElementById('bgMusicPlayer');
            if (!bg_player || !music_playlist.length) {
                return;
            }
            const vol = parseFloat(getCSSVar('--music-volume'));
            bg_player.volume = isNaN(vol) ? 0.3 : vol;
            bg_player.addEventListener('ended', function () {
                return playMusicTrack(randomOtherIndex(music_playlist, current_music_index));
            });
            bg_player.addEventListener('error', function () {
                return playMusicTrack(randomOtherIndex(music_playlist, current_music_index));
            });
            playMusicTrack(Math.floor(Math.random() * music_playlist.length));
        }

        // ===== VIDEO =====

        /**
         * Load Video Playlist
         */
        async function loadVideoPlaylist() {
            if (!VIDEOS) {
                return;
            }

            // Local mock mode: use preview.mp4 from the customguide folder.
            if (MOCK) {
                video_playlist = ['preview.mp4'];
                return;
            }
            try {
                const resp = await fetch('/media/list_videos');
                if (!resp.ok) {
                    throw new Error('HTTP ' + resp.status);
                }
                const data = await resp.json();
                video_playlist = data.files || [];
            }
            catch (e) {
                console.warn('no video playlist:', e.message);
            }
        }
        /**
         * Play Video Track
         */
        function playVideoTrack(index) {
            if (!bg_video_player || !video_playlist.length) {
                return;
            }
            current_video_index = index % video_playlist.length;
            bg_video_player.src = video_playlist[current_video_index];
            if (MOCK) {
                bg_video_player.muted = true;
            }
            bg_video_player.play().catch(function (e) {
                console.warn('video play failed:', e.message);
            });
        }
        /**
         * Setup Video
         */
        function setupVideo() {
            bg_video_player = document.getElementById('bgVideoPlayer');
            if (!bg_video_player) {
                return;
            }
            if (!video_playlist.length) {
                const video_panel = document.getElementById('video-panel');
                if (video_panel) {
                    video_panel.style.display = 'none';
                }
                return;
            }
            const vol = parseFloat(getCSSVar('--video-volume'));
            bg_video_player.volume = isNaN(vol) ? 0.8 : vol;
            let consecutive_errors = 0;
            bg_video_player.addEventListener('ended', function () {
                consecutive_errors = 0;
                playVideoTrack(randomOtherIndex(video_playlist, current_video_index));
            });
            bg_video_player.addEventListener('error', function () {
                consecutive_errors++;
                if (consecutive_errors >= video_playlist.length) {
                    console.warn('all video tracks failed to load, hiding video panel');
                    const video_panel = document.getElementById('video-panel');
                    if (video_panel) {
                        video_panel.style.display = 'none';
                    }
                    return;
                }
                setTimeout(function () {
                    return playVideoTrack(randomOtherIndex(video_playlist, current_video_index));
                }, 1000);
            });
            playVideoTrack(Math.floor(Math.random() * video_playlist.length));
        }

        // ===== TEXT CAROUSEL =====

        /**
         * Load Messages
         */
        async function loadMessages() {
            if (!MESSAGES_PATH) {
                return;
            }
            try {
                const resp = await fetch('/media/json?path=' + encodeURIComponent(MESSAGES_PATH));
                if (!resp.ok) {
                    throw new Error('HTTP ' + resp.status);
                }
                const data = await resp.json();
                messages = data.messages || [];
            }
            catch (e) {
                console.warn('no messages:', e.message);
            }
        }
        /**
         * Show Next Message
         */
        function showNextMessage(index) {
            const title_el = document.getElementById('text-message-title');
            const body_el = document.getElementById('text-message-body');
            if (!title_el || !body_el) {
                return;
            }
            const msg = messages[index % messages.length];
            title_el.style.opacity = '0';
            body_el.style.opacity = '0';
            setTimeout(function () {
                title_el.innerHTML = msg.title || '';
                body_el.textContent = msg.body || '';
                title_el.style.opacity = '1';
                body_el.style.opacity = '1';
            }, 400);
            const default_duration = parseFloat(getCSSVar('--text-carousel-speed')) || 10;
            const duration = (msg.duration || default_duration) * 1000 + 400;
            message_carousel_timer = setTimeout(function () {
                showNextMessage(index + 1);
            }, duration);
        }
        /**
         * Start Text Carousel
         */
        function startTextCarousel() {
            const title_el = document.getElementById('text-message-title');
            const body_el = document.getElementById('text-message-body');
            if (!title_el || !body_el) {
                return;
            }
            if (!messages.length) {
                title_el.textContent = 'FieldStation42';
                body_el.textContent = '';
                return;
            }
            showNextMessage(0);
        }

        // ===== INIT =====

        /**
         * Init
         */
        async function init() {
            await loadTheme(THEME);
            const header_pos = getCSSVar('--header-position').replace(/["']/g, '');
            if (header_pos === 'bottom') {
                document.getElementById('guide-wrapper').classList.add('header-bottom');
            }
            const theme_header = getCSSVar('--header-text').replace(/["']/g, '');
            document.getElementById('header-text').textContent = HEADER_TEXT || theme_header || 'TV Guide';
            const layout_mode = getCSSVar('--layout-mode').replace(/["']/g, '') || 'list';
            if (layout_mode === 'grid') {
                await initGridMode();
            }
            else {
                startClock();
                const music_loaded = loadMusicPlaylist();
                if (MOCK) {
                    mockFetchStations();
                }
                else {
                    await fetchStations();
                }
                await buildGuide();
                startScrolling();
                await music_loaded;
                setupMusic();
            }
        }
        document.addEventListener('DOMContentLoaded', init);
        self.loadTheme = loadTheme;
        self.getCSSVar = getCSSVar;
        self.formatTime12 = formatTime12;
        self.formatDateForAPI = formatDateForAPI;
        self.getPauseDuration = getPauseDuration;
        self.getScrollSpeed = getScrollSpeed;
        self.computeSlotTimes = computeSlotTimes;
        self.mockFetchStations = mockFetchStations;
        self.mockFetchAllSchedules = mockFetchAllSchedules;
        self.fetchStations = fetchStations;
        self.fetchAllSchedules = fetchAllSchedules;
        self.findBlockForSlot = findBlockForSlot;
        self.buildScrollStrip = buildScrollStrip;
        self.stopScrolling = stopScrolling;
        self.buildGuide = buildGuide;
        self.startScrolling = startScrolling;
        self.buildGridDOM = buildGridDOM;
        self.updateGridHeader = updateGridHeader;
        self.createGridProgramBlock = createGridProgramBlock;
        self.buildGridStrip = buildGridStrip;
        self.buildGrid = buildGrid;
        self.startGridScrolling = startGridScrolling;
        self.stopGridScrollingForInteraction = stopGridScrollingForInteraction;
        self.getInteractiveRows = getInteractiveRows;
        self.getProgramsForRow = getProgramsForRow;
        self.getProgramCenterMs = getProgramCenterMs;
        self.findClosestProgramIndex = findClosestProgramIndex;
        self.showGuideToast = showGuideToast;
        self.ensureInteractiveSelectionVisible = ensureInteractiveSelectionVisible;
        self.applyInteractiveSelection = applyInteractiveSelection;
        self.selectInteractiveRow = selectInteractiveRow;
        self.shiftInteractiveWindow = shiftInteractiveWindow;
        self.moveInteractiveHorizontal = moveInteractiveHorizontal;
        self.moveInteractiveVertical = moveInteractiveVertical;
        self.tuneInteractiveSelection = tuneInteractiveSelection;
        self.handleInteractiveKeydown = handleInteractiveKeydown;
        self.initGridInteraction = initGridInteraction;
        self.initGridMode = initGridMode;
        self.startClock = startClock;
        self.randomOtherIndex = randomOtherIndex;
        self.loadMusicPlaylist = loadMusicPlaylist;
        self.playMusicTrack = playMusicTrack;
        self.setupMusic = setupMusic;
        self.loadVideoPlaylist = loadVideoPlaylist;
        self.playVideoTrack = playVideoTrack;
        self.setupVideo = setupVideo;
        self.loadMessages = loadMessages;
        self.showNextMessage = showNextMessage;
        self.startTextCarousel = startTextCarousel;
        self.init = init;
    };
    return self;
})();
