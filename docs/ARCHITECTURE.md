# Project structure

FieldStation42 uses Python 3.10 or newer. Application code is organized by
responsibility, with thin launchers and a separate web application.

```text
bin/
    station42
    fieldPlayer
fs42/
    core/                   Shared configuration, paths, logging, and timing
    tools/
        station/            Administration entry point and Station class
            gui/            Textual administration screens and styles
        field_player/       Playback entry point and FieldPlayer class
        catalog/            Catalog scanning, hints, and database access
        schedule/           Schedule generation, blocks, and database access
        sequence/           Series ordering and sequence persistence
        media/              Media inspection, metadata, and break detection
        guide/              Program guide generation and display
        epg/                Guide cache and scheduled cache refresh
        osd/                On-screen display and logo assets
        overlay/            Now-playing, ticker, and parental-control overlays
        diagnostics/        Local diagnostic display
        web_channel/        Playback of browser-based channels
        cable_box/          Cable-box controls and display
            firmware/       Standalone Pico controller program
        remote_control/     Keyboard and IR remote input
    web/
        app.py              Application factory and server lifecycle
        remote_app.py       Standalone handheld-remote application factory
        core/               Router setup, shared state, and service helpers
        blueprints/
            api/            API routers grouped by resource
            tools/          Page routers, templates, scripts, and styles
        templates/          Shared Jinja page layout
        static/             Shared scripts, themes, and station templates
test/                       Unit and integration tests
```

## Placement rules

`fs42/` contains three source packages: `core`, `tools`, and `web`.

- `core` provides shared application foundations: configuration, logging, paths,
  and timing. It does not own pages or device integrations.
- `tools/<capability>` owns application behavior, including platform-specific
  implementations. Cataloging, playback, display, and controller input follow
  the same placement rule. Platform dependencies do not create another root
  category.
- `web` owns HTTP applications, request schemas, routers, browser templates,
  scripts, and styles. Routers call tool code for application operations.

Assets stay with their consumer. OSD logos and guide-rendering images belong
with their tools; browser assets belong with their page blueprint. The Pico
firmware belongs to the cable-box capability and remains independently
deployable. Command-file transport belongs to `tools/field_player`, while its
HTTP adapter and handheld remote page belong to `web`.

The full console and standalone remote have separate application factories
because their root pages and deployment behavior differ. Both use the same
blueprint and template structure under `web`; neither contains duplicated player
logic.

## Launching the tools

Activate the installed Python environment and run commands from the repository
directory so configuration, content, and runtime paths resolve as configured.

```bash
python bin/station42 --help
python bin/station42 --server
python bin/fieldPlayer --help
python bin/fieldPlayer
```

`station_42.py` and `field_player.py` remain thin compatibility launchers. Existing
command-line flags are accepted by both forms.

System services invoke package modules from the repository directory, for example
`python -m fs42.tools.osd.main`. The Pico listener is a separate program: copy
`fs42/tools/cable_box/firmware/aerial_listener.py` onto the Pico with its CircuitPython dependencies.
It does not import the desktop `fs42` package.

The other controller services run `python -m fs42.tools.cable_box.main` and
`python -m fs42.tools.remote_control.main`. Start the standalone remote with
`python -m uvicorn fs42.web.remote_app:app`. Its `/`, `/api/command`, `/api/status`,
and original script and stylesheet URLs remain available.

## Python code

The administration and playback packages expose `main` through `__init__.py`.
Their `main.py` files parse options and construct the core class. The class owns
the operation's state and coordinates smaller methods. Stateless helpers belong
in utility modules; package constants belong in `_constants.py`.

Use the project's MPL header, grouped imports ordered by line length, explicit
class bases, single-quoted strings, `.format()` interpolation, and multiline RST
docstrings. `.editorconfig` defines whitespace conventions and `.style.yapf`
defines Python formatting.

This is a Python 3 application. FastAPI route signatures and Pydantic models keep
annotations used for request validation and schema generation. FastAPI lifecycle
and request handlers retain asynchronous operations. Qt and hardware integrations
keep the APIs required by their installed libraries.

## Web application

`fs42.web.app.create_app()` builds the FastAPI application. It accepts optional
command and shutdown queues plus server configuration. Build-task results, locks,
and player sampling state belong to that application instance.

Each page lives in `fs42/web/blueprints/tools/<page>/`:

```text
<page>/
    __init__.py
    templates/<page>/index.html
    static/<page>.js
    static/style.css
```

Some display pages have additional theme, image, and music files. Templates extend
the shared Jinja layout. Page scripts expose an `app.tools.<page>` namespace with a
`setup` entry point. Shared request and layout helpers live under
`web/static/utils/`.

Existing page and API URLs remain available. Page assets use
`/static/tools/<page>/`; the existing `/static/bump/`, `/static/ppv/`, and
`/static/customguide/` asset paths also remain available. The shared
`/static/common.js` and `/static/fs42_client.js` URLs resolve to their reorganized
utility scripts.

## Configuration and stored data

Station definitions remain in `confs/`, and server settings remain in
`confs/main_config.json`. Generated files stay under the configured runtime and catalog
directories. Database tables, serialized scheduling-hint names, and saved player
state retain their existing formats.

Python imports now use the package locations shown above. External extensions
that imported former flat modules such as `fs42.catalog_api` should update to
`from fs42.tools.catalog import catalog_api`.

## Validation

Install the development dependencies in the project environment, then run:

```bash
python -m pytest -q
```

`test/test_application_structure.py` covers the application factory, queue
isolation, page and asset routes, request validation, shutdown, launchers, and
saved catalog hints. The existing suites cover cataloging, scheduling, metadata,
sequences, station drafts, and display layout.

Sequence-scanning fixtures create symbolic links. They require a platform and
account that can create those links. Playback and hardware integrations also need
their Linux, MPV, display, and device dependencies for a complete runtime check.
