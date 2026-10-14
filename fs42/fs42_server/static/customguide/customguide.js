const params = new URLSearchParams(window.location.search);
const THEME = params.get('theme') || '80s';
// The 00s/Xfinity-style grid shows three full half-hour columns plus part of a fourth.
const SLOT_COUNT = parseInt(params.get('slots')) || (THEME === '00s' ? 4 : 3);
const HEADER_TEXT = params.get('header') || null;
const PAUSE_OVERRIDE = params.get('pause');
const MOCK = params.get('mock') === '1';
const INTERACTIVE = params.get('interactive') === '1';
const USE_META = params.get('use_meta') !== '0';
const SHOW_DESCRIPTION = ['1', 'true'].includes((params.get('show_description') || '').toLowerCase());
const MUSIC_PATH = params.get('music');
const VIDEOS = params.get('videos') !== 'false';
const LIVE_PREVIEW = params.get('live_preview') === '1';
const MESSAGES_PATH = params.get('messages');
const LOOP = params.get('loop') !== '0';
let RANDOM_START = params.get('random_start') === '1';

if (LIVE_PREVIEW && !MOCK) {
  document.documentElement.classList.add('live-preview-mode');
}

let stations = [];

// list-mode scroll state
let animFrame = null;
let scrollY = 0;
let pauseUntil = 0;

// grid-mode scroll state
let gridAnimFrame = null;
let gridScrollY = 0;
let gridPauseUntil = 0;

// interactive grid state
let interactiveRowIndex = 0;
let interactiveProgramIndex = 0;
let interactiveSlotOffset = 0;
let interactiveKeyBusy = false;
let guideToastTimer = null;

// Fixed starting point for the mock 00s schedule.
// Keeping this constant makes programs stay attached to their actual mock airtimes
// while the visible guide window moves left/right.
const MOCK_00S_SCHEDULE_START = (() => {
  const now = new Date();
  now.setMinutes(Math.floor(now.getMinutes() / 30) * 30, 0, 0);
  return now.getTime();
})();

// music
let musicPlaylist = [];
let currentMusicIndex = 0;
let bgPlayer = null;

// video
let videoPlaylist = [];
let currentVideoIndex = 0;
let bgVideoPlayer = null;

// text carousel
let messages = [];
let messageCarouselTimer = null;


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
      } else {
        resolve();
      }
    });
    document.head.appendChild(link);
  });
}

function getCSSVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function formatTime12(date) {
  return date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
}

// Compact guide-clock formats used by the early-2000s cable UI.
function formatTime00s(date, shortSuffix = false) {
  const parts = date.toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true
  }).replace(' ', '').toLowerCase();

  if (!shortSuffix) return parts;
  return parts.replace('am', 'a').replace('pm', 'p');
}

function formatRange00s(startMs, endMs) {
  const start = new Date(Number(startMs));
  const end = new Date(Number(endMs));

  const startHour = start.getHours() % 12 || 12;
  const startMinutes = start.getMinutes();
  const startText = startMinutes === 0
    ? `${startHour}`
    : `${startHour}:${String(startMinutes).padStart(2, '0')}`;

  const endMinutes = end.getMinutes();
  const endHour = end.getHours() % 12 || 12;
  const endSuffix = end.getHours() >= 12 ? 'p' : 'a';
  const endText = endMinutes === 0
    ? `${endHour}${endSuffix}`
    : `${endHour}:${String(endMinutes).padStart(2, '0')}${endSuffix}`;

  return `${startText}-${endText}`;
}

function formatDateForAPI(date) {
  const y = date.getFullYear();
  const mo = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  const h = String(date.getHours()).padStart(2, '0');
  const mi = String(date.getMinutes()).padStart(2, '0');
  const s = String(date.getSeconds()).padStart(2, '0');
  return `${y}-${mo}-${d}T${h}:${mi}:${s}`;
}

function getPauseDuration() {
  if (PAUSE_OVERRIDE) return parseFloat(PAUSE_OVERRIDE) * 1000;
  const match = getCSSVar('--scroll-pause').match(/([\d.]+)\s*s/);
  return match ? parseFloat(match[1]) * 1000 : 5000;
}

function getScrollSpeed() {
  const val = parseFloat(getCSSVar('--scroll-speed'));
  return (!isNaN(val) && val > 0) ? val : 1.1;
}

function computeSlotTimes(offsetSlots = 0) {
  const now = new Date();
  const base = new Date(now.getFullYear(), now.getMonth(), now.getDate(),
    now.getHours(), Math.floor(now.getMinutes() / 30) * 30, 0, 0);
  base.setMinutes(base.getMinutes() + offsetSlots * 30);
  const slots = [];
  for (let i = 0; i < SLOT_COUNT; i++) {
    const start = new Date(base.getTime() + i * 30 * 60 * 1000);
    slots.push({ start, end: new Date(start.getTime() + 30 * 60 * 1000) });
  }
  return slots;
}

// mock data for local scroll testing (?mock=1)
const MOCK_SHOWS = [
  'Late Night Movie', 'The Evening News', 'Sports Center', 'Nature Documentary',
  'Sitcom Reruns', 'Talk Show', 'Crime Drama', 'Cooking Hour', 'Saturday Morning Cartoons',
  'Local Weather Update', 'Classic Film', 'Music Videos', 'Game Show Marathon',
  'Science Fiction Theater', 'Western Double Feature', 'Home Shopping', 'News Magazine',
  'Children\'s Programming', 'Live Sports', 'Comedy Special'
];

function mockFetchStations() {
  // The 00s mock intentionally mirrors the visual reference so local CSS work can be
  // compared against a stable channel lineup instead of randomly generated channel names.
  if (THEME === '00s') {
    stations = [
      { channel_number: 24, network_name: 'USA',   network_long_name: 'USA Network', has_schedule: true },
      { channel_number: 25, network_name: 'ALT',   network_long_name: 'ALT Sports', has_schedule: true },
      { channel_number: 26, network_name: 'FS-RM', network_long_name: 'Fox Sports Rocky Mountain', has_schedule: true },
      { channel_number: 27, network_name: 'FX-W',  network_long_name: 'FX West', has_schedule: true },
      { channel_number: 28, network_name: 'NIK',   network_long_name: 'Nickelodeon', has_schedule: true },
      { channel_number: 29, network_name: 'TOON',  network_long_name: 'Cartoon Network', has_schedule: true },
      { channel_number: 30, network_name: 'DSC',   network_long_name: 'Discovery', has_schedule: true },
      { channel_number: 31, network_name: 'TBS',   network_long_name: 'TBS', has_schedule: true },
      { channel_number: 32, network_name: 'ESPN',  network_long_name: 'ESPN', has_schedule: true },
      { channel_number: 33, network_name: 'AMC',   network_long_name: 'AMC', has_schedule: true }
    ];
    return;
  }

  stations = Array.from({ length: 24 }, function (_, i) {
    const num = i + 2;
    return {
      channel_number: num,
      network_name: 'ch' + num,
      network_long_name: 'Channel ' + num,
      has_schedule: true
    };
  });
}

function mockFetchAllSchedules(slots) {
  if (THEME === '00s') {
    const schedules = {};
    const halfHour = 30 * 60 * 1000;
    const guideStart = slots[0].start.getTime();
    const guideEnd = slots[slots.length - 1].end.getTime();

    const lineups = {
      'USA': [
        ['Law & Order: Criminal Intent', 60, 'Detectives investigate a complex criminal case.', 'drama'],
        ['Walker...', 60, 'Crime-fighting action continues.', 'drama']
      ],
      'ALT': [
        ['George Karl', 30, 'Sports talk and analysis.', 'sports'],
        ['NHL Hockey', 90, 'Live professional hockey coverage.', 'sports']
      ],
      'FS-RM': [
        ['College Basketball', 60, 'College basketball coverage.', 'sports'],
        ['World Poker', 60, 'Tournament poker action.', 'default']
      ],
      'FX-W': [
        ['Big Daddy', 60, 'A comedy feature presentation.', 'movie'],
        ['Malcolm in...', 60, 'A family comedy series.', 'default']
      ],
      'NIK': [
        ['SpongeBob SquarePants', 30, 'A chipper sea sponge and his nautical neighbors make waves in the deep-sea city of Bikini...', 'kids'],
        ['Fairly OddParents', 30, 'A boy gets help from his magical fairy godparents.', 'kids'],
        ['Zoey 101', 60, 'Life at Pacific Coast Academy.', 'kids']
      ],
      'TOON': [
        ['Cartoon Cartoons', 30, 'Animated comedy favorites.', 'kids'],
        ['Teen Titans', 30, 'Superhero action.', 'kids'],
        ['Ed, Edd n Eddy', 60, 'Neighborhood cartoon comedy.', 'kids']
      ],
      'DSC': [
        ['MythBusters', 60, 'Putting popular myths to the test.', 'default'],
        ['Dirty Jobs', 60, 'Unusual jobs from around the country.', 'default']
      ],
      'TBS': [
        ['Seinfeld', 30, 'Classic sitcom.', 'default'],
        ['Friends', 30, 'Comedy series.', 'default'],
        ['Movie', 60, 'Feature presentation.', 'movie']
      ],
      'ESPN': [
        ['SportsCenter', 60, 'Sports news and highlights.', 'sports'],
        ['College Football', 60, 'Live college football.', 'sports']
      ],
      'AMC': [
        ['Classic Movie', 120, 'A classic feature presentation.', 'movie']
      ]
    };

    for (const station of stations) {
  const blocks = [];
  const lineup =
    lineups[station.network_name] ||
    [['Programming', 30, '', 'default']];

  // Always generate the mock schedule from the same fixed point in time.
  // This is important: if we started at guideStart every time, advancing
  // the guide would simply redraw the same shows in the same positions.
  let cursor = MOCK_00S_SCHEDULE_START;
  let i = 0;

  // Build forward until we've covered the entire visible guide window.
  while (cursor < guideEnd) {
    const item = lineup[i % lineup.length];
    const duration = item[1] * 60 * 1000;
    const programEnd = cursor + duration;

    // Only include programs that overlap the currently visible window.
    // A program may begin before guideStart; createGridProgramBlock()
    // will clip it against the left edge, which makes the programming
    // visibly move left as the user advances the time bar.
    if (programEnd > guideStart) {
      blocks.push({
        start_time: new Date(cursor).toISOString(),
        end_time: new Date(programEnd).toISOString(),
        title: item[0],
        meta: {
          plot: item[2],
          guide_category: item[3],
          rating: station.network_name === 'NIK' ? 'TV Y' : ''
        }
      });
    }

    cursor = programEnd;
    i++;
  }

  schedules[station.network_name] = blocks;
}

    return schedules;
  }

  const schedules = {};
  const slotMs = 30 * 60 * 1000;
  for (const station of stations) {
    const blocks = [];
    let t = slots[0].start.getTime();
    const end = slots[slots.length - 1].end.getTime();
    while (t < end) {
      const duration = (Math.floor(Math.random() * 3) + 1) * slotMs;
      const title = MOCK_SHOWS[Math.floor(Math.random() * MOCK_SHOWS.length)];
      blocks.push({ start_time: new Date(t).toISOString(), end_time: new Date(t + duration).toISOString(), title });
      t += duration;
    }
    schedules[station.network_name] = blocks;
  }
  return schedules;
}

async function fetchStations() {
  const all = await window.fs42Common.fetchChannels();
  stations = all.filter(s => !s.hidden);
}

async function fetchAllSchedules(slots, includeMeta) {
  if (!stations.length) return {};

  const overallStart = slots[0].start;
  const overallEnd = slots[slots.length - 1].end;

  try {
    return await window.fs42Common.fetchGuideSchedules(
      formatDateForAPI(overallStart),
      formatDateForAPI(overallEnd),
      includeMeta
    );
  } catch (e) {
    console.error('error fetching schedules', e);
    return {};
  }
}


// ===== LIST MODE (80s) =====

function findBlockForSlot(blocks, slotStart) {
  for (const block of blocks) {
    const bStart = new Date(block.start_time);
    const bEnd = new Date(block.end_time);
    if (bStart <= slotStart && bEnd > slotStart) {
      return { block, continued: bStart < slotStart };
    }
  }
  return null;
}

function buildScrollStrip(slots, schedules) {
  const strip = document.createElement('div');
  strip.id = 'guide-scroll-strip';

  const channelAfter = getCSSVar('--channel-position').replace(/["']/g, '') === 'after';
  const offairText = getCSSVar('--offair-text').replace(/^["']|["']$/g, '') || 'Offair';

  for (const slot of slots) {
    const heading = document.createElement('div');
    heading.className = 'time-slot-heading';
    heading.textContent = formatTime12(slot.start);
    strip.appendChild(heading);

    for (const station of stations) {
      const row = document.createElement('div');
      row.className = 'listing-row';
      if (channelAfter) row.classList.add('channel-after');

      const channelInfo = document.createElement('span');
      channelInfo.className = 'channel-info';

      const numSpan = document.createElement('span');
      numSpan.className = 'channel-number';
      numSpan.textContent = station.channel_number || '?';

      const nameSpan = document.createElement('span');
      nameSpan.className = 'channel-name';
      const name = station.network_name;
      nameSpan.textContent = name.length > 10 ? name.slice(0, 10) + '…' : name;

      channelInfo.appendChild(numSpan);
      channelInfo.appendChild(nameSpan);

      const titleSpan = document.createElement('span');
      titleSpan.className = 'show-title';

      const result = findBlockForSlot(schedules[station.network_name] || [], slot.start);
      if (result) {
        const t = result.block.title || offairText;
        titleSpan.textContent = t.length > 20 ? t.slice(0, 20) + '…' : t;
        if (result.continued) row.classList.add('continued');
      } else {
        titleSpan.textContent = offairText;
      }

      row.appendChild(channelInfo);
      row.appendChild(titleSpan);
      strip.appendChild(row);
    }
  }

  return strip;
}

function stopScrolling() {
  if (animFrame) {
    cancelAnimationFrame(animFrame);
    animFrame = null;
  }
}

async function buildGuide() {
  const slots = computeSlotTimes();
  const schedules = MOCK ? mockFetchAllSchedules(slots) : await fetchAllSchedules(slots);
  const listings = document.getElementById('guide-listings');
  listings.innerHTML = '';
  listings.appendChild(buildScrollStrip(slots, schedules));
}

function startScrolling() {
  stopScrolling();

  const listings = document.getElementById('guide-listings');
  const strip = document.getElementById('guide-scroll-strip');
  if (!strip) return;

  const pxPerMs = getScrollSpeed() / 50;
  const pauseMs = getPauseDuration();

  scrollY = 0;
  strip.style.transform = 'translateY(0)';
  pauseUntil = performance.now() + pauseMs;

  let lastTime = null;

  function tick(now) {
    if (now < pauseUntil) {
      animFrame = requestAnimationFrame(tick);
      return;
    }

    const maxScroll = strip.offsetHeight - listings.clientHeight;

    if (maxScroll <= 0) {
      setTimeout(async function () { await buildGuide(); startScrolling(); }, pauseMs);
      return;
    }

    if (lastTime !== null) scrollY += pxPerMs * (now - lastTime);
    lastTime = now;

    if (scrollY >= maxScroll) {
      strip.style.transform = `translateY(-${maxScroll}px)`;
      lastTime = null;
      setTimeout(async function () { await buildGuide(); startScrolling(); }, pauseMs);
      return;
    }

    strip.style.transform = `translateY(-${scrollY}px)`;
    animFrame = requestAnimationFrame(tick);
  }

  animFrame = requestAnimationFrame(tick);
}


// ===== GRID MODE (90s / 00s) =====

function buildGridDOM() {
  const listings = document.getElementById('guide-listings');
  listings.classList.add('grid-mode');

  if (THEME === '00s') {
    listings.classList.add('xfinity-00s');
    listings.innerHTML = `
      <div id="top-panel" class="xfinity-top-panel">
        <div id="text-panel" class="xfinity-info-panel">
          <div class="xfinity-brand-strip">
            <div class="comcast-logo"><img src="images/comcast_logo.png"></div>
            <div class="xfinity-listings-block">
              <div class="xfinity-listings-title">TV Listings</div>
              <div class="xfinity-clock-line">
                <!-- <span class="xfinity-envelope" aria-hidden="true"></span> -->
                <span id="clock"></span>
              </div>
            </div>
            <div class="tv-guide-badge" aria-label="TV Guide">
              <img src="images/tv_guide_logo.png">
            </div>
          </div>

          <div class="xfinity-program-details">
            <div class="xfinity-program-heading">
              <div id="selected-program-title">Program Title</div>
              <div id="selected-channel-label"></div>
            </div>
            <div class="xfinity-program-subrow">
              <div id="selected-program-time"></div>
              <div id="selected-program-icons">
                <!--
                 <span id="selected-program-rating">TV Y</span>
                 <span class="xfinity-lock-icon" aria-label="locked"></span>
                -->
              </div>
            </div>
            <div id="selected-program-description"></div>
          </div>
        </div>

        <div id="video-panel">
          <video id="bgVideoPlayer" preload="auto" playsinline></video>
        </div>
      </div>

      <div id="grid-wrapper">
        <div id="grid-header">
          <div class="grid-channel-stub">
            <span class="xfinity-today">Today</span>
            <span class="xfinity-prev-arrow" aria-hidden="true"></span>

            <div class="clock-icon">
              <img src="images/clock_icon.png">
            </div>
          </div>
        </div>
        <div id="grid-listings"></div>
      </div>

      <div id="guide-promo" aria-hidden="true">
        <div class="promo-card">
        </div>
      </div>
    `;
  } else {
    listings.innerHTML = `
      <div id="top-panel">
        <div id="video-panel"><video id="bgVideoPlayer" preload="auto"></video></div>
        <div id="text-panel">
          <div id="text-message-title"></div>
          <div id="text-message-body"></div>
        </div>
      </div>
      <div id="grid-wrapper">
        <div id="grid-header"><div class="grid-channel-stub"><span id="clock"></span></div></div>
        <div id="grid-listings"></div>
      </div>
    `;

    const videoSide = getCSSVar('--video-side').replace(/["']/g, '') || 'left';
    if (videoSide === 'right') {
      document.getElementById('video-panel').style.order = '1';
      document.getElementById('text-panel').style.order = '0';
    }
  }

  bgVideoPlayer = document.getElementById('bgVideoPlayer');
}

function updateGridHeader(slots) {
  const header = document.getElementById('grid-header');
  if (!header) return;
  // Remove old slot labels, keep the channel stub
  const stub = header.querySelector('.grid-channel-stub');
  header.innerHTML = '';
  if (stub) {
    header.appendChild(stub);
  } else {
    const newStub = document.createElement('div');
    newStub.className = 'grid-channel-stub';
    header.appendChild(newStub);
  }
  for (const slot of slots) {
    const slotEl = document.createElement('div');
    slotEl.className = 'grid-time-slot';
    slotEl.textContent = THEME === '00s' ? formatTime00s(slot.start, true) : formatTime12(slot.start);
    header.appendChild(slotEl);
  }
}

function getProgramCategory(block, station) {
  const meta = block && block.meta ? block.meta : {};
  if (meta.guide_category) return String(meta.guide_category).toLowerCase();

  const text = [
    block && block.title,
    meta.title,
    meta.type,
    meta.genre,
    Array.isArray(meta.genres) ? meta.genres.join(' ') : meta.genres,
    station && station.network_name
  ].filter(Boolean).join(' ').toLowerCase();

  if (/(sports|football|basketball|baseball|hockey|soccer|golf|tennis|espn|fox sports|nhl|nba|nfl|mlb)/.test(text)) return 'sports';
  if (/(movie|film|feature|cinema)/.test(text)) return 'movie';
  if (/(kids|children|cartoon|nick|nik|toons|disney|spongebob|zoey|fairly)/.test(text)) return 'kids';
  return 'default';
}


function createGridProgramBlock(block, guideStartMs, guideEndMs, totalMs, now, station) {
  const bStart = new Date(block.start_time);
  const bEnd = new Date(block.end_time);

  if (bEnd.getTime() <= guideStartMs || bStart.getTime() >= guideEndMs) return null;

  const visStart = Math.max(bStart.getTime(), guideStartMs);
  const visEnd = Math.min(bEnd.getTime(), guideEndMs);

  const leftPct = (visStart - guideStartMs) / totalMs * 100;
  const widthPct = (visEnd - visStart) / totalMs * 100;

  const el = document.createElement('div');
  el.className = 'grid-program-block';
  el.dataset.startMs = String(bStart.getTime());
  el.dataset.endMs = String(bEnd.getTime());
  el.dataset.title = block.title || 'Untitled';

  const meta = USE_META && block.meta;
  const description = (meta && (meta.plot || meta.description)) || block.description || '';
  const rating = (meta && (meta.rating || meta.content_rating)) || '';
  const category = getProgramCategory(block, station);

  el.dataset.description = description;
  el.dataset.rating = typeof rating === 'string' ? rating : '';
  el.dataset.category = category;
  el.classList.add(`program-category-${category}`);

  if (bStart <= now && bEnd > now) el.classList.add('current');

  el.style.left = leftPct + '%';
  el.style.width = `calc(${widthPct}% - 2px)`;

  const titleSpan = document.createElement('span');
  titleSpan.className = 'program-title';
  titleSpan.textContent = block.title || 'Untitled';
  el.appendChild(titleSpan);

  let desc = meta && meta.plot;
  let isEpisodeTitle = false;
  if (meta && meta.type === 'episode' && !SHOW_DESCRIPTION && meta.title) {
    desc = meta.title;
    isEpisodeTitle = true;
  }
  if (desc) {
    const descSpan = document.createElement('span');
    descSpan.className = isEpisodeTitle ? 'program-desc is-episode-title' : 'program-desc';
    descSpan.textContent = desc;
    el.appendChild(descSpan);
  }

  return el;
}

function buildGridStrip(slots, schedules) {
  const strip = document.createElement('div');
  strip.id = 'grid-scroll-strip';

  const guideStartMs = slots[0].start.getTime();
  const guideEndMs = slots[slots.length - 1].end.getTime();
  const totalMs = guideEndMs - guideStartMs;
  const now = new Date();
  const offairText = getCSSVar('--offair-text').replace(/^["']|["']$/g, '') || 'No Info';

  for (let stationIndex = 0; stationIndex < stations.length; stationIndex++) {
    const station = stations[stationIndex];
    const row = document.createElement('div');
    row.className = 'grid-row';
    row.dataset.stationIndex = String(stationIndex);
    row.dataset.channelNumber = String(station.channel_number ?? '');
    row.dataset.channelName = String(station.network_name || '');
    row.dataset.channelLongName = String(station.network_long_name || station.network_name || '');

    const channelDiv = document.createElement('div');
    channelDiv.className = 'grid-channel';

    const numSpan = document.createElement('span');
    numSpan.className = 'channel-number';
    numSpan.textContent = station.channel_number || '?';

    const nameSpan = document.createElement('span');
    nameSpan.className = 'channel-name';
    nameSpan.textContent = station.network_name;

    channelDiv.appendChild(numSpan);
    channelDiv.appendChild(nameSpan);
    row.appendChild(channelDiv);

    const programsDiv = document.createElement('div');
    programsDiv.className = 'grid-programs';

    const blocks = schedules[station.network_name] || [];

    if (!station.has_schedule || !blocks.length) {
      const noInfo = document.createElement('div');
      noInfo.className = 'grid-program-block';
      noInfo.dataset.startMs = String(guideStartMs);
      noInfo.dataset.endMs = String(guideEndMs);
      noInfo.dataset.title = station.network_long_name || offairText;
      noInfo.dataset.description = '';
      noInfo.dataset.rating = '';
      noInfo.dataset.category = 'default';
      noInfo.classList.add('program-category-default');
      noInfo.style.left = '0';
      noInfo.style.width = '100%';
      const t = document.createElement('span');
      t.className = 'program-title';
      t.textContent = station.network_long_name || offairText;
      noInfo.appendChild(t);
      programsDiv.appendChild(noInfo);
    } else {
      for (const block of blocks) {
        const blockEl = createGridProgramBlock(block, guideStartMs, guideEndMs, totalMs, now, station);
        if (blockEl) programsDiv.appendChild(blockEl);
      }
    }

    row.appendChild(programsDiv);
    strip.appendChild(row);
  }

  return strip;
}

async function buildGrid() {
  const slots = computeSlotTimes(INTERACTIVE ? interactiveSlotOffset : 0);
  updateGridHeader(slots);
  const schedules = MOCK ? mockFetchAllSchedules(slots) : await fetchAllSchedules(slots, USE_META);
  const gridListings = document.getElementById('grid-listings');
  gridListings.innerHTML = '';
  gridListings.appendChild(buildGridStrip(slots, schedules));
}

function startGridScrolling() {
  if (gridAnimFrame) {
    cancelAnimationFrame(gridAnimFrame);
    gridAnimFrame = null;
  }

  const listings = document.getElementById('grid-listings');
  const strip = document.getElementById('grid-scroll-strip');
  if (!strip || !listings) return;

  const pxPerMs = getScrollSpeed() / 50;
  const pauseMs = getPauseDuration();

  // Clean up any previous clone
  const existingClone = document.getElementById('grid-scroll-strip-clone');
  if (existingClone) existingClone.remove();

  let clone;
  const originalHeight = strip.scrollHeight;

  // Loop guide if true.
  if (LOOP) {
    clone = strip.cloneNode(true);
    clone.id = 'grid-scroll-strip-clone';
    clone.setAttribute('aria-hidden', 'true');
    strip.parentElement.appendChild(clone);
    clone.style.transform = `translateY(${originalHeight}px)`;
  }
      // Random channel start
      if (RANDOM_START) {
        gridScrollY = Math.random() * originalHeight;
        RANDOM_START = false;
      } else if (!LOOP) {
        gridScrollY = 0;
      }

  strip.style.transform = 'translateY(0)';
  gridPauseUntil = LOOP ? 0 : performance.now() + pauseMs;

  let lastTime = null;

  function tick(now) {
    if (now < gridPauseUntil) {
      gridAnimFrame = requestAnimationFrame(tick);
      return;
    }

    // Loop guide if true.
    if (LOOP) {
      if (lastTime !== null) gridScrollY += pxPerMs * (now - lastTime);
      lastTime = now;

      if (gridScrollY >= originalHeight) {
        gridScrollY -= originalHeight;
        if (gridAnimFrame) {
          cancelAnimationFrame(gridAnimFrame);
          gridAnimFrame = null;
        }
        buildGrid().then(startGridScrolling);
        return;
      }

      strip.style.transform = `translateY(-${gridScrollY}px)`;
      clone.style.transform = `translateY(${originalHeight - gridScrollY}px)`;
      gridAnimFrame = requestAnimationFrame(tick);

    } else {
      const maxScroll = strip.offsetHeight - listings.clientHeight;

      if (maxScroll <= 0) {
        setTimeout(async function () { await buildGrid(); startGridScrolling(); }, pauseMs);
        return;
      }

      if (lastTime !== null) gridScrollY += pxPerMs * (now - lastTime);
      lastTime = now;

      if (gridScrollY >= maxScroll) {
        strip.style.transform = `translateY(-${maxScroll}px)`;
        lastTime = null;
        setTimeout(async function () { await buildGrid(); startGridScrolling(); }, pauseMs);
        return;
      }

      strip.style.transform = `translateY(-${gridScrollY}px)`;
      gridAnimFrame = requestAnimationFrame(tick);
    }
  }

  gridAnimFrame = requestAnimationFrame(tick);
}

function stopGridScrollingForInteraction() {
  if (gridAnimFrame) {
    cancelAnimationFrame(gridAnimFrame);
    gridAnimFrame = null;
  }

  const clone = document.getElementById('grid-scroll-strip-clone');
  if (clone) clone.remove();
}

function getInteractiveRows() {
  return Array.from(document.querySelectorAll('#grid-scroll-strip .grid-row'));
}

function getProgramsForRow(row) {
  if (!row) return [];
  return Array.from(row.querySelectorAll('.grid-program-block'));
}

function getProgramCenterMs(program) {
  const start = Number(program?.dataset.startMs);
  const end = Number(program?.dataset.endMs);
  if (Number.isFinite(start) && Number.isFinite(end)) return start + (end - start) / 2;
  return Date.now();
}

function findClosestProgramIndex(programs, targetMs) {
  if (!programs.length) return 0;

  let bestIndex = 0;
  let bestDistance = Infinity;
  programs.forEach(function (program, index) {
    const start = Number(program.dataset.startMs);
    const end = Number(program.dataset.endMs);
    if (Number.isFinite(start) && Number.isFinite(end) && targetMs >= start && targetMs < end) {
      bestIndex = index;
      bestDistance = -1;
      return;
    }

    if (bestDistance < 0) return;
    const distance = Math.abs(getProgramCenterMs(program) - targetMs);
    if (distance < bestDistance) {
      bestDistance = distance;
      bestIndex = index;
    }
  });

  return bestIndex;
}

function showGuideToast(message, isError = false) {
  let toast = document.getElementById('guide-action-toast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'guide-action-toast';
    toast.setAttribute('aria-live', 'polite');
    document.body.appendChild(toast);
  }

  toast.textContent = message;
  toast.classList.toggle('error', isError);
  toast.classList.add('visible');

  if (guideToastTimer) clearTimeout(guideToastTimer);
  guideToastTimer = setTimeout(function () {
    toast.classList.remove('visible');
  }, 1400);
}

function ensureInteractiveSelectionVisible() {
  const rows = getInteractiveRows();
  const row = rows[interactiveRowIndex];
  const listings = document.getElementById('grid-listings');
  const strip = document.getElementById('grid-scroll-strip');
  if (!row || !listings || !strip) return;

  const rowTop = row.offsetTop;
  const rowBottom = rowTop + row.offsetHeight;
  const viewportHeight = listings.clientHeight;

  if (rowTop < gridScrollY) {
    gridScrollY = rowTop;
  } else if (rowBottom > gridScrollY + viewportHeight) {
    gridScrollY = rowBottom - viewportHeight;
  }

  const maxScroll = Math.max(0, strip.scrollHeight - viewportHeight);
  gridScrollY = Math.max(0, Math.min(gridScrollY, maxScroll));
  strip.style.transform = `translateY(-${gridScrollY}px)`;
}

function updateSelectedProgramInfo() {
  if (THEME !== '00s') return;

  const rows = getInteractiveRows();
  const row = rows[interactiveRowIndex];
  if (!row) return;

  const programs = getProgramsForRow(row);
  const program = programs[interactiveProgramIndex];
  if (!program) return;

  const titleEl = document.getElementById('selected-program-title');
  const channelEl = document.getElementById('selected-channel-label');
  const timeEl = document.getElementById('selected-program-time');
  const descEl = document.getElementById('selected-program-description');
  const ratingEl = document.getElementById('selected-program-rating');

  if (titleEl) titleEl.textContent = program.dataset.title || 'No Info';
  if (channelEl) {
    const channelNum = row.dataset.channelNumber || '';
    const channelName = row.dataset.channelName || '';
    channelEl.textContent = `${channelNum} ${channelName}`.trim();
  }
  if (timeEl) timeEl.textContent = formatRange00s(program.dataset.startMs, program.dataset.endMs);
  if (descEl) {
    descEl.textContent = program.dataset.description ||
      `More information about ${program.dataset.title || 'this program'} is not available.`;
  }
  if (ratingEl) ratingEl.textContent = program.dataset.rating || 'TV Y';
}


function applyInteractiveSelection() {
  const rows = getInteractiveRows();
  if (!rows.length) return;

  interactiveRowIndex = Math.max(0, Math.min(interactiveRowIndex, rows.length - 1));
  document.querySelectorAll('.grid-row.guide-selected-row').forEach(el => el.classList.remove('guide-selected-row'));
  document.querySelectorAll('.grid-program-block.guide-selected').forEach(function (el) {
    el.classList.remove('guide-selected');
    el.removeAttribute('aria-selected');
  });

  const row = rows[interactiveRowIndex];
  const programs = getProgramsForRow(row);
  if (!programs.length) return;

  interactiveProgramIndex = Math.max(0, Math.min(interactiveProgramIndex, programs.length - 1));
  row.classList.add('guide-selected-row');

  const program = programs[interactiveProgramIndex];
  program.classList.add('guide-selected');
  program.setAttribute('aria-selected', 'true');

  ensureInteractiveSelectionVisible();
  updateSelectedProgramInfo();
}

function selectInteractiveRow(rowIndex, targetMs) {
  const rows = getInteractiveRows();
  if (!rows.length) return;

  interactiveRowIndex = Math.max(0, Math.min(rowIndex, rows.length - 1));
  const programs = getProgramsForRow(rows[interactiveRowIndex]);
  interactiveProgramIndex = findClosestProgramIndex(programs, targetMs);
  applyInteractiveSelection();
}

async function shiftInteractiveWindow(delta, targetMs) {
  const nextOffset = Math.max(0, interactiveSlotOffset + delta);
  if (nextOffset === interactiveSlotOffset) {
    showGuideToast('LIVE');
    return;
  }

  interactiveSlotOffset = nextOffset;
  const currentRow = interactiveRowIndex;
  await buildGrid();

  const rows = getInteractiveRows();
  const row = rows[Math.max(0, Math.min(currentRow, rows.length - 1))];
  const programs = getProgramsForRow(row);
  interactiveRowIndex = Math.max(0, Math.min(currentRow, rows.length - 1));
  interactiveProgramIndex = findClosestProgramIndex(programs, targetMs);
  applyInteractiveSelection();
}

async function moveInteractiveHorizontal(direction) {
  const rows = getInteractiveRows();
  const row = rows[interactiveRowIndex];
  const programs = getProgramsForRow(row);
  if (!programs.length) return;

  const nextIndex = interactiveProgramIndex + direction;
  if (nextIndex >= 0 && nextIndex < programs.length) {
    interactiveProgramIndex = nextIndex;
    applyInteractiveSelection();
    return;
  }

  const current = programs[interactiveProgramIndex];
  const start = Number(current?.dataset.startMs) || Date.now();
  const end = Number(current?.dataset.endMs) || Date.now();
  const targetMs = direction > 0 ? end + 1 : start - 1;
  await shiftInteractiveWindow(direction, targetMs);
}

function moveInteractiveVertical(direction) {
  const rows = getInteractiveRows();
  if (!rows.length) return;

  const currentPrograms = getProgramsForRow(rows[interactiveRowIndex]);
  const currentProgram = currentPrograms[interactiveProgramIndex];
  if (!currentProgram) return;

  const programStartMs = Number(currentProgram.dataset.startMs);

  // The leftmost visible grid slot is the start of the current guide window.
  const slots = computeSlotTimes(INTERACTIVE ? interactiveSlotOffset : 0);
  const leftmostGridTimeMs = slots[0].start.getTime();

  // Normally preserve the selected program's actual start time.
  // If that start is off-screen to the left, use the visible guide's
  // left edge instead.
  const targetMs = Number.isFinite(programStartMs)
    ? Math.max(programStartMs, leftmostGridTimeMs)
    : leftmostGridTimeMs;

  selectInteractiveRow(
    interactiveRowIndex + direction,
    targetMs
  );
}

async function tuneInteractiveSelection() {
  const rows = getInteractiveRows();
  const row = rows[interactiveRowIndex];
  if (!row) return;

  const channelNumber = row.dataset.channelNumber;
  if (!channelNumber) {
    showGuideToast('NO CHANNEL', true);
    return;
  }

  if (MOCK) {
    showGuideToast(`TUNE CH ${channelNumber} (MOCK)`);
    console.log(`Interactive guide mock tune: channel ${channelNumber}`);
    return;
  }

  try {
    await window.fs42Api.get(`player/channels/${encodeURIComponent(channelNumber)}`);
  } catch (e) {
    console.error('interactive guide tune failed', e);
    showGuideToast('TUNE FAILED', true);
  }
}

async function handleInteractiveKeydown(event) {
  if (!INTERACTIVE || interactiveKeyBusy) return;

  let action = null;
  if (event.key === 'ArrowUp' || event.key === 'PageUp') action = 'up';
  else if (event.key === 'ArrowDown' || event.key === 'PageDown') action = 'down';
  else if (event.key === 'ArrowLeft') action = 'left';
  else if (event.key === 'ArrowRight') action = 'right';
  else if (event.key === 'Enter') action = 'enter';
  else if (event.key === 'Home') action = 'home';
  if (!action) return;

  event.preventDefault();
  event.stopPropagation();
  interactiveKeyBusy = true;

  try {
    if (action === 'up') moveInteractiveVertical(-1);
    else if (action === 'down') moveInteractiveVertical(1);
    else if (action === 'left') await moveInteractiveHorizontal(-1);
    else if (action === 'right') await moveInteractiveHorizontal(1);
    else if (action === 'enter') await tuneInteractiveSelection();
    else if (action === 'home') {
      interactiveSlotOffset = 0;
      await buildGrid();
      const rows = getInteractiveRows();
      const programs = getProgramsForRow(rows[interactiveRowIndex]);
      interactiveProgramIndex = findClosestProgramIndex(programs, Date.now());
      applyInteractiveSelection();
      showGuideToast('LIVE');
    }
  } finally {
    interactiveKeyBusy = false;
  }
}

function initGridInteraction() {
  stopGridScrollingForInteraction();
  gridScrollY = 0;
  document.body.classList.add('guide-interactive');

  const rows = getInteractiveRows();
  if (rows.length) {
    // Start on the fifth mock row (NIK / SpongeBob) so the local preview closely
    // matches the supplied Comcast/Xfinity reference. Real channel data starts at row 0.
    interactiveRowIndex = (MOCK && THEME === '00s' && rows.length > 4) ? 4 : 0;
    const programs = getProgramsForRow(rows[interactiveRowIndex]);
    const currentIndex = programs.findIndex(program => program.classList.contains('current'));
    interactiveProgramIndex = currentIndex >= 0 ? currentIndex : findClosestProgramIndex(programs, Date.now());
    applyInteractiveSelection();
  }

  document.addEventListener('keydown', handleInteractiveKeydown);

  const listings = document.getElementById('grid-listings');
  listings.addEventListener('click', function (event) {
    const program = event.target.closest('.grid-program-block');
    const row = event.target.closest('.grid-row');
    if (!program || !row) return;

    const rowsNow = getInteractiveRows();
    interactiveRowIndex = rowsNow.indexOf(row);
    interactiveProgramIndex = getProgramsForRow(row).indexOf(program);
    applyInteractiveSelection();
  });
}


async function initGridMode() {
  document.getElementById('guide-header').style.display = 'none';
  const oldClock = document.getElementById('clock');
  if (oldClock) oldClock.remove();
  buildGridDOM();
  startClock();


  const mediaLoaded = Promise.all([
    loadMusicPlaylist(),
    loadVideoPlaylist(),
    loadMessages()
  ]);

  if (MOCK) mockFetchStations(); else await fetchStations();
  await buildGrid();

  if (INTERACTIVE) {
    initGridInteraction();
  } else {
    // The 00s layout always shows program details in the upper-left panel, even when
    // running in its original passive/auto-scroll mode.
    if (THEME === '00s') {
      const rows = getInteractiveRows();
      if (rows.length) {
        interactiveRowIndex = (MOCK && rows.length > 4) ? 4 : 0;
        const programs = getProgramsForRow(rows[interactiveRowIndex]);
        const currentIndex = programs.findIndex(program => program.classList.contains('current'));
        interactiveProgramIndex = currentIndex >= 0 ? currentIndex : 0;
        updateSelectedProgramInfo();
      }
    }
    startGridScrolling();
  }

  await mediaLoaded;
  setupMusic();
  setupVideo();
  startTextCarousel();
}


// ===== CLOCK =====

function startClock() {
  const el = document.getElementById('clock');
  if (!el) return;
  const tick = () => {
    el.textContent = THEME === '00s' ? formatTime00s(new Date(), false) : formatTime12(new Date());
  };
  tick();
  setInterval(tick, 1000);
}


// ===== RANDOM PLAYBACK =====

function randomOtherIndex(playlist, current) {
  if (playlist.length <= 1) return 0;
  let next;
  do { next = Math.floor(Math.random() * playlist.length); } while (next === current);
  return next;
}


// ===== MUSIC =====

async function loadMusicPlaylist() {
  // The live station underneath supplies the guide audio.
  if (!MOCK && LIVE_PREVIEW) return;

  try {
    if (MUSIC_PATH) {
      const resp = await fetch('/media/list?path=' + encodeURIComponent(MUSIC_PATH));
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const data = await resp.json();
      musicPlaylist = data.files || [];
    } else {
      // Only fall back to the bundled json if the theme allows it
      const autoload = getCSSVar('--music-autoload').replace(/["']/g, '');
      if (autoload === 'false') return;
      const resp = await fetch('music_playlist.json');
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const data = await resp.json();
      musicPlaylist = data.music_files || [];
    }
  } catch (e) {
    console.warn('no music playlist:', e.message);
  }
}

function playMusicTrack(index) {
  if (!bgPlayer || !musicPlaylist.length) return;
  currentMusicIndex = index % musicPlaylist.length;
  bgPlayer.src = musicPlaylist[currentMusicIndex];
  bgPlayer.play().catch(function () {
    document.addEventListener('click', () => bgPlayer.play(), { once: true });
  });
}

function setupMusic() {
  bgPlayer = document.getElementById('bgMusicPlayer');
  if (!bgPlayer || !musicPlaylist.length) return;

  const vol = parseFloat(getCSSVar('--music-volume'));
  bgPlayer.volume = isNaN(vol) ? 0.3 : vol;
  bgPlayer.addEventListener('ended', () => playMusicTrack(randomOtherIndex(musicPlaylist, currentMusicIndex)));
  bgPlayer.addEventListener('error', () => playMusicTrack(randomOtherIndex(musicPlaylist, currentMusicIndex)));
  playMusicTrack(Math.floor(Math.random() * musicPlaylist.length));
}


// ===== VIDEO =====

async function loadVideoPlaylist() {
  if (!VIDEOS) return;
  if (!MOCK && LIVE_PREVIEW) return;

  // Local mock mode: use preview.mp4 from the customguide folder.
  if (MOCK) {
    videoPlaylist = ['preview.mp4'];
    return;
  }

  try {
    const resp = await fetch('/media/list_videos');
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const data = await resp.json();
    videoPlaylist = data.files || [];
  } catch (e) {
    console.warn('no video playlist:', e.message);
  }
}

function playVideoTrack(index) {
  if (!bgVideoPlayer || !videoPlaylist.length) return;
  currentVideoIndex = index % videoPlaylist.length;
  bgVideoPlayer.src = videoPlaylist[currentVideoIndex];
  if (MOCK) {
    bgVideoPlayer.muted = true;
  }
  bgVideoPlayer.play().catch(function (e) {
    console.warn('video play failed:', e.message);
  });
}

function setupVideo() {
  bgVideoPlayer = document.getElementById('bgVideoPlayer');
  if (!bgVideoPlayer) return;

  // In the real guide the preview is not a second video player. The WebRender
  // window is transparent here, so the still-running MPV channel underneath is
  // literally what appears in the preview rectangle.
  if (!MOCK && LIVE_PREVIEW) {
    const videoPanel = document.getElementById('video-panel');
    if (videoPanel) videoPanel.classList.add('live-channel-preview');
    bgVideoPlayer.removeAttribute('src');
    bgVideoPlayer.style.display = 'none';
    return;
  }

  if (!videoPlaylist.length) {
    const videoPanel = document.getElementById('video-panel');
    if (videoPanel) {
      if (THEME === '00s') {
        videoPanel.classList.add('video-unavailable');
      } else {
        videoPanel.style.display = 'none';
      }
    }
    return;
  }

  const vol = parseFloat(getCSSVar('--video-volume'));
  bgVideoPlayer.volume = isNaN(vol) ? 0.8 : vol;

  let consecutiveErrors = 0;

  bgVideoPlayer.addEventListener('ended', function () {
    consecutiveErrors = 0;
    playVideoTrack(randomOtherIndex(videoPlaylist, currentVideoIndex));
  });

  bgVideoPlayer.addEventListener('error', function () {
    consecutiveErrors++;
    if (consecutiveErrors >= videoPlaylist.length) {
      console.warn('all video tracks failed to load, hiding video panel');
      const videoPanel = document.getElementById('video-panel');
      if (videoPanel) {
        if (THEME === '00s') {
          videoPanel.classList.add('video-unavailable');
        } else {
          videoPanel.style.display = 'none';
        }
      }
      return;
    }
    setTimeout(() => playVideoTrack(randomOtherIndex(videoPlaylist, currentVideoIndex)), 1000);
  });

  playVideoTrack(Math.floor(Math.random() * videoPlaylist.length));
}


// ===== TEXT CAROUSEL =====

async function loadMessages() {
  if (!MESSAGES_PATH) return;
  try {
    const resp = await fetch('/media/json?path=' + encodeURIComponent(MESSAGES_PATH));
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const data = await resp.json();
    messages = data.messages || [];
  } catch (e) {
    console.warn('no messages:', e.message);
  }
}

function showNextMessage(index) {
  const titleEl = document.getElementById('text-message-title');
  const bodyEl = document.getElementById('text-message-body');
  if (!titleEl || !bodyEl) return;

  const msg = messages[index % messages.length];

  titleEl.style.opacity = '0';
  bodyEl.style.opacity = '0';

  setTimeout(function () {
    titleEl.innerHTML = msg.title || '';
    bodyEl.textContent = msg.body || '';
    titleEl.style.opacity = '1';
    bodyEl.style.opacity = '1';
  }, 400);

  const defaultDuration = parseFloat(getCSSVar('--text-carousel-speed')) || 10;
  const duration = ((msg.duration || defaultDuration) * 1000) + 400;
  messageCarouselTimer = setTimeout(function () {
    showNextMessage(index + 1);
  }, duration);
}

function startTextCarousel() {
  const titleEl = document.getElementById('text-message-title');
  const bodyEl = document.getElementById('text-message-body');
  if (!titleEl || !bodyEl) return;

  if (!messages.length) {
    titleEl.textContent = 'FieldStation42';
    bodyEl.textContent = '';
    return;
  }

  showNextMessage(0);
}


// ===== INIT =====

async function init() {
  await loadTheme(THEME);

  const headerPos = getCSSVar('--header-position').replace(/["']/g, '');
  if (headerPos === 'bottom') document.getElementById('guide-wrapper').classList.add('header-bottom');

  const themeHeader = getCSSVar('--header-text').replace(/["']/g, '');
  document.getElementById('header-text').textContent = HEADER_TEXT || themeHeader || 'TV Guide';

  const layoutMode = getCSSVar('--layout-mode').replace(/["']/g, '') || 'list';

  if (layoutMode === 'grid') {
    await initGridMode();
  } else {
    startClock();
    const musicLoaded = loadMusicPlaylist();
    if (MOCK) mockFetchStations(); else await fetchStations();
    await buildGuide();
    startScrolling();
    await musicLoaded;
    setupMusic();
  }
}

document.addEventListener('DOMContentLoaded', init);
