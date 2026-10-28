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
        settings.json       Web defaults, widget configuration, and registration options
        core/               Router setup, shared state, and service helpers
        blueprints/
            api/            API routers grouped by resource
            web_interface/  Web console and handheld remote pages and assets
            menu/           Pi-facing menus and browser-based channel displays
            widgets/        Web console controls with templates, scripts, and styles
            menu_widgets/   Pi menu clocks and panels with their own templates and assets
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

Console pages and the standalone handheld remote live in
`fs42/web/blueprints/web_interface/<page>/`. The console guide and its embedded
guide frame also belong here. Pi-facing customguide, on-demand, PPV, and bump
screens live in `fs42/web/blueprints/menu/<page>/`:

```text
<page>/
    __init__.py
    templates/<page>/index.html
    static/<page>.js
    static/style.css
```

Some display pages have additional theme, image, and music files. Page scripts
expose `app.web_interface.<page>` or `app.menu.<page>`, with an explicit `setup()`
entry point and methods on `self`. Keep page markup in Jinja templates, styling
in CSS, and browser interaction and changing data in JavaScript. Shared request
and behavior helpers live under `web/static/utils/`.

`core/_pages.py` discovers API and page packages that expose an `APIRouter` named
`router`. Add a page package without editing a central router or asset list.
The page module declares `TITLE` and can declare `DESCRIPTION`, `MENU_TITLE`,
`MENU_GROUP`, `MENU_ORDER`, and `HEADING`. Set `HIDE_FROM_MENU = True` for pages
that do not belong in console navigation. `REQUIRES_PLAYER = True` hides a
navigation item until a player queue is connected. `STANDALONE = True` selects
the handheld-remote deployment. `STATIC_ALIASES` lists older asset prefixes.

Give page routes names such as `catalog.index`, and render them with
`bu.render_page(request, __name__)` from `core/blueprint.py`. Templates use
`sub_url_for('catalog')` for page links and
`sub_static('catalog', 'catalog.js')` for page assets.

`templates/base.html` loads each page's script and styles once and calls its
`setup()` after the markup. Regular console pages extend
`web_interface/index.html` and fill `tool_content`; this layout includes
navigation built from page metadata. Display-only pages, the handheld remote,
and Pi menus use layouts without console navigation. Configurable selectors,
search controls, and log displays live under `blueprints/widgets/`. The station editor keeps its Monaco
dependency in its own `page_sources` block.

Render widgets with `include_widget('selector', {'attributes': {'id': 'channel'}})`.
The widget configuration merges instance overrides over the application's defaults
without modifying them. Widget packages are discovered automatically; templates live
in `templates/<name>/widget.html`, and files in `static/` are included once per page.
JavaScript widget instances keep independent state by control ID. Use
`render_attributes()` for HTML attributes and Jinja's `tojson` filter when passing
configuration into scripts.

Browser routes are exported by the application into `window.fs42Routes` and are also
available at `/web/routes`. `urlFor('api.catalogs.get_catalog',
{network_name: name})` builds an encoded URL from a registered endpoint. The shared
API client uses the page's origin and these URLs, including configured deployment
prefixes. Existing path-based callers remain supported by the same resolver.

`core/errors.py` centralizes HTML error pages, JSON API errors, and traceback logging.
API validation responses retain their structured `detail` list. Unexpected failures
return a generic explanation; HTML traceback details appear only when web `debug`
is explicitly enabled. Top-level `errorMessage`, `showError`, and `reportError` format browser errors and displays them
as text in an accessible notice or a page's existing error area. Dynamic HTML
renderers escape catalog, schedule, station, and search text with the shared helper.

Existing page and API URLs remain available. Page assets use
`/static/web_interface/<page>/` or `/static/menu/<page>/`. Compatibility paths
under `/static/tools/<page>/`, `/static/bump/`, `/static/ppv/`,
`/static/on_demand/`, and `/static/customguide/` remain available. The shared
`/static/common.js` and `/static/fs42_client.js` URLs resolve to their reorganized
utility scripts.

## Configuration and stored data

Station definitions remain in `confs/`, and server settings remain in
`confs/main_config.json`. Generated files stay under the configured runtime and catalog
directories. Database tables, serialized scheduling-hint names, and saved player
state retain their existing formats.

Web settings load from `fs42/web/settings.json`, then an optional JSON file named by
`FS42_WEB_SETTINGS`, then the `web` dictionary in `confs/main_config.json` (or the
application factory's `server_conf`). Nested dictionaries merge; lists and scalar
values replace their defaults. Both web application factories accept these settings.

For example, this `web` section hides diagnostics, mounts the catalog page below
`/console`, and adds `/service` to the summary API routes:

```json
{
    "web": {
        "disabled_blueprints": ["web_interface.diagnostics"],
        "url_prefixes": {
            "web_interface.catalog": "/console",
            "api.summary": "/service"
        },
        "widgets": {
            "selector": {"config": {"label": "Choose station:"}}
        }
    }
}
```

`url_prefixes` prepend to each blueprint's declared page/API URLs and page asset
mounts. Qualified names distinguish API and page packages; short package names
are also accepted. Disabling a group or parent package skips its descendants.
Use `root_path`, for example `/station`, for deployment behind a proxy mounted
under that path. Leave it empty for ordinary direct hosting. Default URLs are
unchanged when these overrides are absent. The environment override file contains
the web settings directly, without the outer `web` key.

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

Shared scripts in `web/static/utils/` expose top-level functions, including
`urlFor`, `fetchURL`, `apiGet`, `apiPost`, `initConsole`, and `escapeHtml`.
They do not use the page and widget namespaces.

Routing utilities follow the shared web-app helper conventions: `ajaxURL(url,
callback, method)` returns response text; `ajaxPost(url, data, callback, type)`
posts JSON, or the `main-form` fields when data is omitted; and
`ajaxEndpoint(endpoint, args, callback)` waits for routes and retrieves text.
All three return promises as well as accepting callbacks. `urlFor(endpoint,
args, filename)` consumes path arguments, appends an optional static filename,
and encodes remaining query arguments. `convertArgsToStr`, `splitUrl`,
`isInternal`, `redirect`, and `getPageTitle` are shared global helpers.
`$ROUTES` is populated from the rendered route data or `/web/routes` by
`loadRoutes()` and `routingInit()`. The JSON adapters remain available to
existing console and Pi pages. Redirects use normal browser navigation so
current players and polling timers are released when a page is replaced.

Blueprint scripts declare behavior directly as `self.render`, `self.onChange`,
`self.loadData`, or other named methods at namespace scope. `self.setup()` only
initializes page state, creates widget/viewer instances, starts initial loads,
and binds handlers. Viewer and widget classes are defined alongside setup,
with instance behavior on their methods. Small callbacks stay with the action
that needs their local state; whole page implementations are not defined in setup.

`menu_clock` owns the Pi menus' once-per-second local-time updates. Include it
with `include_widget('menu_clock', {'attributes': {'id': 'clock'}})`. Defaults
under `menu_widgets.menu_clock.config` control the locale, `Intl.DateTimeFormat`
options, and compact lowercase AM/PM formatting. Each instance renders
immediately, updates once per second, and stops when replaced, detached, or
unloaded. The custom guide and on-demand menu retain their existing clock IDs
and styling; their page scripts no longer manage clock timers.

`menu_top_panel` owns the shared menu panel, branding assets, and CSS. Its
`video_panel` option defaults to `false`; `title` defaults to `null` and is
rendered as escaped text when provided. Without a preview, the text panel uses
the full width. The native-renderer hook remains `id="video-panel"` when enabled.
Use a Jinja call block for the details area instead of passing raw HTML in settings:

```jinja
{% call include_widget('menu_top_panel', {'video_panel': true, 'title': 'TV Listings'}) %}
    <h2>{{ program.title }}</h2>
    <p>{{ program.description }}</p>
{% endcall %}
```

The caller block inherits its page's template context and normal escaping. Its
HTML belongs to the page, so each menu can use its own structure and dynamic
control IDs. Omit the call block for an empty details area. The nested clock
can be configured through the `clock` dictionary; use unique clock and panel
attribute IDs when rendering multiple panels on one page. The guide keeps its
existing selected-program IDs and continues to update their content in JavaScript.

`menu_bottom_panel` (widget name) renders the `menu-bottom-panel` element and
owns its stylesheet. It accepts a Jinja call block just like `menu_top_panel`:

```jinja
{% call include_widget('menu_bottom_panel') %}
    <p>{{ message }}</p>
{% endcall %}
```

Omitting the call block produces an empty panel. Attribute overrides support
custom IDs and accessibility attributes. The guide's empty decorative panel
uses `aria-hidden="true"`; panels with meaningful content remain accessible by default.

Console widgets (`selector`, `search`, and `log_display`) live under
`blueprints/widgets/`. Pi widgets (`menu_clock`, `menu_top_panel`, and
`menu_bottom_panel`) live under `blueprints/menu_widgets/`. Both families use
`include_widget()` and caller blocks. Defaults are stored under the matching
`widgets` or `menu_widgets` settings key. Static URLs and named mounts follow
the family, for example `/static/menu_widgets/menu_clock/menu_clock.css` and
`menu_widgets.menu_top_panel.static`. JavaScript uses `app.widgets` for console
widgets and `app.menu_widgets` for Pi widgets. Each page loads assets from its
own widget family.

Both customguide and on-demand use `menu_top_panel` and `menu_bottom_panel`.
On-demand supplies its heading and selection text through the top panel's caller
block, enables the native video preview, and places `od-navigation` inside the
bottom panel's caller block. The shared widgets own both panel layouts and their
styles; the on-demand page owns its choices, title details, and navigation behavior.
