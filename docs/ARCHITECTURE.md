# FieldStation42 Architecture

This document maps the repository by responsibility and records the compatibility rules
used while the project is reorganized.

## Entry Points

- `station_42.py` builds catalogs and schedules and starts the configuration server.
- `field_player.py` runs the television playback loop.
- `install/` contains installation and service definitions.

Keep these entry points stable. Internal modules may move behind compatibility imports.

## Package Map

### Playback

`fs42/player/`

- `station_player.py` owns channel playback and MPV integration.
- `reception.py` owns reception state and channel-change video effects.

The legacy modules `fs42.station_player` and `fs42.reception` remain import-compatible
while callers are migrated.

### Scheduling

The scheduling implementation is still in the legacy flat package:

- `liquid_*.py`
- `fluid_*.py`
- `sequence*.py`
- `schedule_hint.py`
- `live_schedule_agent.py`
- `marathon_agent.py`
- `autobump_agent.py`

This will be moved as a separate refactor so playback changes do not alter schedule
behavior at the same time.

### Catalog and Media

The catalog and media implementation is still in the legacy flat package:

- `catalog*.py`
- `media_processor.py`
- `metadata_io.py`
- `nfo_agent.py`
- `title_parser.py`
- `reel_cutter.py`
- `path_query.py`

### Server and User Interfaces

- `fs42/fs42_server/` contains the HTTP API and browser UI.
- `fs42/osd/` contains the on-screen display.
- `fs42/overlay/` contains playback overlays.
- `fs42/ux/` contains the terminal UI.
- `fs42/webrender/` contains browser rendering support.
- `fs42/diagchannel/` contains the diagnostic channel.

### Hardware

- `fs42/pi/` contains Raspberry Pi cable-box and remote-control integration.
- `fs42/pico/` contains Pico integration.
- `fs42/remote/` contains the standalone remote server.

## Refactor Rules

1. Move one subsystem at a time.
2. Do not mix file moves with behavior changes.
3. Preserve established import paths with explicit compatibility modules.
4. Keep root entry points stable until their internals are thin enough to move safely.
5. Run the existing test suite after every structural phase.
6. Remove compatibility modules only after all in-repo callers have migrated.
7. Prefer explicit package boundaries over new cross-package helper abstractions.
