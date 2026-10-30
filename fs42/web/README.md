# 📡 FieldStation42 Server API Guide

Welcome to the FieldStation42 Server API! This is your one-stop guide to understanding and using the comprehensive REST API that powers your broadcasting station. Whether you're setting up your system or controlling live playback, this API has got you covered.

## 🚀 Quick Start

First things first - let's get your server running!

### Starting the Server

```bash
python3 station_42.py --server
```

This starts both the API server and web console. Visit **http://localhost:4242** to access the beautiful web interface!

### Default Configuration

Your server runs with these defaults (configurable in `main_config.json`):
```json
{
  "server_host": "0.0.0.0",
  "server_port": 4242
}
```

## 🎯 API Overview

The FieldStation42 API is organized around two main concepts:

- **🔧 Build-Time APIs**: System administration, configuration, and content management
- **📺 Play-Time APIs**: Live player control, monitoring, and viewer interaction

All endpoints return JSON responses and follow RESTful conventions.

---

## 🔧 Build-Time APIs

*For setting up your station, managing content, and system administration*

### 🏠 Web Console

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Main web console interface |
| `GET` | `/remote` | Remote control interface |

### 📊 Station Summary & Overview

#### Get Complete Station Summary
```http
GET /summary/
```
Returns comprehensive overview of all stations including catalog and schedule info.

**Response Example:**
```json
{
  "summary_data": [
    {
      "network_name": "PublicDomain",
      "channel_number": 1,
      "catalog_summary": {
        "entry_count": 42,
        "total_duration": 12345.67
      },
      "schedule_summary": {
        "network_name": "PublicDomain",
        "start": "2025-07-13T00:00:00",
        "end": "2025-07-14T00:00:00"
      }
    }
  ]
}
```

#### List All Stations
```http
GET /summary/stations
```
Get a simple list of all station network names.

**Response:**
```json
{
  "network_names": ["PublicDomain", "PBS", "ClassicMovies"]
}
```

### 📅 Schedule Management

#### Get Schedule Summaries
```http
GET /summary/schedules
```
Returns schedule summaries for all stations.

```http
GET /summary/schedules/{network_name}
```
Get schedule summary for a specific station.

#### Get Detailed Schedule Blocks
```http
GET /schedules/{network_name}?start=YYYY-MM-DDTHH:MM:SS&end=YYYY-MM-DDTHH:MM:SS
```

Retrieve detailed schedule blocks with optional time filtering.

**Example:** `GET /schedules/PublicDomain?start=2025-07-13T00:00:00&end=2025-07-14T00:00:00`

**Response:**
```json
{
  "network_name": "PublicDomain",
  "schedule_blocks": [
    {
      "content": [...],
      "start_time": "2025-07-13T00:00:00",
      "end_time": "2025-07-13T00:30:00",
      "title": "quickstop",
      "plan": [...],
      "break_strategy": "standard",
      "break_info": {...}
    }
  ]
}
```

### 📚 Catalog Management

#### Get All Catalog Entries
```http
GET /catalogs/{network_name}
```

#### Search Catalog
```http
GET /catalogs/search/{network_name}?query=search_term
```

#### Get Catalog Summaries
```http
GET /summary/catalogs
```
Returns entry counts for all station catalogs.

### ⚙️ Station Configuration

#### Get Station Config
```http
GET /stations/{network_name}
```
Returns complete configuration for a specific station.

### 🎨 Themes & Styling

#### Get Available Themes
```http
GET /about/themes
```
Lists all available CSS themes for the web interface.

### 🛠️ Build Operations

*Asynchronous operations that return task IDs for status tracking*

#### Rebuild Catalog
```http
POST /build/catalog/{network_name}
```
Rebuilds catalog for specified station (use "all" for all stations).

**Returns:** `{"task_id": "uuid-string"}`

**Check Status:**
```http
GET /build/catalog/status/{task_id}
```

#### Reset Schedule
```http
POST /build/schedule/reset/{network_name}
```
Completely rebuilds schedule for specified station.

**Check Status:**
```http
GET /build/schedule/reset/status/{task_id}
```

#### Add Time to Schedule
```http
POST /build/schedule/add_time/{amount}
```
Adds specified time period to all station schedules (e.g., "1d", "12h", "30m").

**Check Status:**
```http
GET /build/schedule/add_time/status/{task_id}
```

---

## 📺 Play-Time APIs

*For controlling live playback and monitoring your broadcast*

### 🎮 Player Control

#### Channel Control
```http
GET /player/channels/{channel}
```
Change channel. Use a number, "up", or "down".

**Examples:**
- `/player/channels/5` - Switch to channel 5
- `/player/channels/up` - Channel up
- `/player/channels/down` - Channel down

#### Show Program Guide
```http
POST /player/channels/guide
```
Display the on-screen program guide.

#### Stop Player
```http
GET /player/commands/stop
POST /player/commands/stop
```
Gracefully stop the player.

### 🔊 Volume Control

| Endpoint | Description |
|----------|-------------|
| `GET/POST /player/volume/up` | Increase volume by 5% |
| `GET/POST /player/volume/down` | Decrease volume by 5% |
| `GET/POST /player/volume/mute` | Toggle mute on/off |

**Response Example:**
```json
{
  "action": "up",
  "method": "pulseaudio",
  "status": "success",
  "message": "Volume increased by 5%",
  "volume": "75%"
}
```

### 📡 System Monitoring

#### Player Status
```http
GET /player/status
```
Get current player status and program information.

#### System Information
```http
GET /player/info
```
Comprehensive system information including CPU temperature, memory usage, and load averages.

**Response Example:**
```json
{
  "temperature_c": 49.4,
  "temperature_f": 121,
  "temp_source": "vcgencmd",
  "memory": {
    "total_gb": 8.0,
    "available_gb": 6.2,
    "used_gb": 1.8,
    "used_percent": 22.5
  },
  "cpu": {
    "cores": 4,
    "load_1min": 0.15,
    "load_5min": 0.18,
    "load_15min": 0.22,
    "load_percent": 3.8
  },
  "system": {
    "platform": "Linux",
    "architecture": "aarch64",
    "hostname": "fieldstation42"
  }
}
```

#### Connection Status
```http
GET /player/status/queue_connected
```
Check if the player command queue is connected.

---

## 🎯 Pro Tips for Developers

### 📅 Date Format
Always use ISO format for date/time parameters: `YYYY-MM-DDTHH:MM:SS`

### 🔄 Asynchronous Operations
Build operations return task IDs. Always check status endpoints to monitor progress:

```javascript
// Start rebuild
const response = await fetch('/build/catalog/PublicDomain', {method: 'POST'});
const {task_id} = await response.json();

// Monitor progress
const checkStatus = async () => {
  const status = await fetch(`/build/catalog/status/${task_id}`);
  const {status: taskStatus, log} = await status.json();
  
  if (taskStatus === 'done') {
    console.log('Rebuild complete!');
  } else if (taskStatus === 'error') {
    console.error('Rebuild failed:', log);
  } else {
    setTimeout(checkStatus, 1000); // Check again in 1 second
  }
};
```

### 🎵 Volume Control
The API automatically detects and uses the best available audio system:
1. **PulseAudio** (pactl) - Most Linux desktops
2. **ALSA** (amixer) - Raspberry Pi and embedded systems  
3. **WirePlumber** (wpctl) - Modern PipeWire systems

### 🔍 Error Handling
All endpoints return detailed error messages. Always check the response:

```javascript
const response = await fetch('/schedules/NonExistentStation');
if (!response.ok) {
  const error = await response.json();
  console.error('API Error:', error.detail);
}
```

### 🌐 Cross-Origin Requests
The server supports CORS for web development. You can make requests from any origin during development.

---

## 🚀 Example Workflows

### Setting Up a New Station

1. **Check current stations:** `GET /summary/stations`
2. **Build catalog:** `POST /build/catalog/MyNewStation`
3. **Monitor progress:** `GET /build/catalog/status/{task_id}`
4. **Build schedule:** `POST /build/schedule/reset/MyNewStation`
5. **Verify setup:** `GET /summary/`

### Monitoring Live Broadcast

1. **Check player status:** `GET /player/status`
2. **Monitor system health:** `GET /player/info`  
3. **Control playback:** `GET /player/channels/up`
4. **Adjust volume:** `POST /player/volume/up`

### Searching and Managing Content

1. **Search catalog:** `GET /catalogs/search/PublicDomain?query=comedy`
2. **Get schedule:** `GET /schedules/PublicDomain`
3. **Add more content time:** `POST /build/schedule/add_time/1d`

---

## 🔮 Coming Soon

We're constantly improving FieldStation42! Here's what's on the roadmap:

### Build-Time Enhancements
- **Sequence Builder**: `/build/sequences/{network_name}`
- **Breakpoint Manager**: `/build/breakpoints/{network_name}`
- **Bulk Operations**: Multi-station management tools

### Play-Time Features  
- **OSD Control**: `/player/osd/display` - Custom on-screen messages
- **Advanced Commands**: System halt, safe shutdown, restart operations
- **WebSocket Endpoints**: Real-time status updates and live controls

---

## 📞 Need Help?

- **Web Console**: Visit http://localhost:4242 for the graphical interface
- **API Docs**: This document (you're reading it!)
- **Source Code**: Check `app.py` and `blueprints/api/` for implementation details

Remember: FieldStation42 is designed to be fun and easy to use. If something seems complicated, we probably need to make it simpler! 🎉

---

*Happy Broadcasting! 📡✨*


### YouTube in On Demand

Open **YouTube** in the web console navigation to add a YouTube channel URL,
`@handle`, or channel ID. Remove a channel from the same page. Saved channels live
in the existing runtime SQLite database, independently of the station catalog.

On the television, open **On Demand → YouTube**, choose a saved channel, and select
an upload. Its details appear in the shared top panel. Open the upload and choose
**Play** to play it once through the existing MPV instance. The remote Back button
returns through the menus; no on-screen Back button is added.

The latest 30 public videos from the channel's Videos tab are listed newest first
in pages of 10. YouTube Shorts are excluded. Metadata is
cached for 10 minutes across the web and player processes; revisiting a channel
after that refreshes it. Removing a channel also removes its upload cache.

Install the updated `install/requirements.in` in the application's virtual
environment. YouTube uses the paired `yt-dlp` and `yt-dlp-ejs` versions there, plus
**Node.js 22+ or Deno 2+** on the player's PATH for YouTube's JavaScript challenges.
MPV must include its standard `ytdl_hook` script. The player locates yt-dlp in its
own Python environment before falling back to PATH. Keep the extractor and EJS
script versions updated together when YouTube changes. Private, paid, and
sign-in-only videos are not supported by this interface.

YouTube playback selects H.264 video up to 1080p at 30 fps and AAC audio, avoiding
4K AV1/VP9 software decoding on the Pi 4. MPV's codec-aware output hook can then
use the hardware decoder and direct Wayland output. YouTube uses 45 seconds of
read-ahead with a 64 MiB cache limit and uses the audio clock for frame timing on older
Wayland builds. The prior format and timing options are restored after playback;
local media and live streams retain their existing buffering settings.

API endpoints:

- `GET /on-demand/youtube/channels`: saved channels.
- `POST /on-demand/youtube/channels`: add or update with `{"url":"@channel"}`.
- `DELETE /on-demand/youtube/channels/{channel_id}`: remove a channel.
- `GET /on-demand/youtube/channels/{channel_id}/uploads?page=0`: recent uploads.
- `POST /on-demand/youtube/channels/{channel_id}/play/{video_id}`: validate a saved
  channel's listed upload and queue single playback. Direct arbitrary URLs are
  not accepted.


### On Demand playback overlay

Selecting a video first opens its details screen, with the description above a
bottom row of Return, Play / Resume, and Play from the beginning symbol buttons.
Play / Resume is initially selected; its label updates as the viewer moves between
actions. Return restores the previous listing and selection.

Both local titles and YouTube uploads keep resume positions in the runtime database.
History is capped at 500 videos across both sources. Saving progress refreshes a
video's recency; the least recently watched entries are removed when the limit is exceeded.
The player checkpoints every five seconds and when playback stops. Play / Resume
starts at that position, or zero for an unwatched video. Play from the beginning
starts at zero. Reaching the end clears the resume position. Failed starts and
denied parental authorization preserve existing progress. Playback POST endpoints
accept an optional `{"start_over": true}` body; omitted options default to resume.

The `on_demand_controls` menu widget draws a transport bar over the existing native
MPV video. It does not create another video player or move playback into the guide
preview. It shows the title/source, elapsed time, total duration, green progress,
and symbol controls for rewind, play/pause, and fast-forward.

The bar appears at playback start and when transport or navigation controls are
used, then hides after four seconds while playing. It remains visible when paused
or buffering. Back dismisses it without leaving the video. Use left/right on the
remote to preview a position on the timeline and OK to seek; up selects the symbol
buttons and down returns to the timeline. The timeline also supports pointer or
touch scrubbing. Rewind and fast-forward move ten seconds per press.

Native playback sends position updates through the retained browser's queue at
most four times per second. Hidden controls do not poll timestamps or repaint.
Timeline requests carry a per-video session ID, and the player ignores stale
sessions and clamps seeks to the video's duration. Controls and the playback
session are cleared when the video ends or the channel changes.

### Shared controls

The web remote, physical remote, menus, and playback overlay use the shared action
catalog in `fs42/core/controls.py`. `GET /controls` lists the current deployment's
actions and argument schemas; `POST /controls/dispatch` validates and dispatches
an action:

```json
{"action": "playback.seek_relative", "arguments": {"seconds": -10}}
```

Browser code calls `sendControl('playback.seek_relative', {seconds: -10})`.
Buttons declare their behavior as `data-control="playback.seek_relative"` and
`data-control-args='{"seconds":-10}'`. The shared `ControlBindings` utility handles
touch, mouse, and keyboard activation, including buttons added after setup.
Destroy the binding before setting it up again. Page-local display behavior stays
in the page's action handlers.

Keyboard mappings come from the same catalog through `navigationAction(event)`.
On Demand navigation follows the actual button positions through `SpatialNavigator`,
so grid column counts are not duplicated in JavaScript. The player resolves which
menu or playback controls own focus. Existing API endpoints remain available for
older integrations, and the standalone handheld remote keeps its file transport.
