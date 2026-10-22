# Shared display service

`field_player` starts one separate Qt process for channel/status text, volume, station logos,
now-playing metadata, parental-control prompts, tickers, and NFO media information. Playback and
PIN validation stay in the player. Closing a panel does not stop the service.

The player reuses an already running service. It stops the service on shutdown only when it started
that service itself. If that player disconnects unexpectedly, the service also exits. Other client
connections own their individual presentations; disconnecting them removes their panels.

## Presentation behavior

- Status text and volume retain their configured display durations and positions.
- Logos retain station selection, animation, feature/break suppression, opacity, and permanent-display settings.
- Now-playing metadata stays visible until replaced or hidden by the player.
- Parental-control digits and errors update directly; PIN validation remains in the player.
- A ticker hides after its requested scroll repetitions. A second active ticker is rejected.
- NFO information retains its configured appearance and beginning/end fades for long clips.

`run_now_playing`, `run_ticker`, and `run_parental_controls` return presentation handles rather than
child processes. Use `handle.hide()`, `handle.update(...)`, and `handle.is_active()` to control them.
The PIN launcher now takes `(network_name, theme_name='classic')`; it does not require a queue.
Only command-line callers use the optional blocking `handle.wait()` operation.

## Resource use

OSD status files are watched through filesystem notifications. Each changed document is read once
and shared between its displays. Visibility expiry uses single-shot deadlines; permanent static
content does not need a repaint timer. Animation runs only while the corresponding content is visible.
PIN updates do not poll a queue, and process signals wake Qt through a socket rather than a heartbeat.

Overlay windows cover their content rather than the entire screen. NFO text is rendered once and
reused throughout fades. Custom font families are registered once. OSD configuration uses lightweight
standard-library dataclasses with normalization instead of loading a general-purpose validation runtime.
Existing JSON option names, alignment values, defaults, and hybrid-display behavior are preserved.

A local Windows/offscreen comparison against commit `4959e73` on October 22, 2026 measured:

| Display state | Previous resident memory | Combined resident memory |
| --- | ---: | ---: |
| Idle OSD | 53.46 MiB | 43.80 MiB |
| OSD with now-playing, PIN prompt, and ticker | 183.86 MiB | 49.21 MiB |
| Idle after closing overlays | 53.46 MiB | 48.56 MiB |

Private memory was 31.06 versus 19.78 MiB idle, and 92.16 versus 22.66 MiB active. The benchmark
includes complete process trees, including Windows virtual-environment launchers. It isolates display
processes and does not measure the rest of playback. Five-second CPU samples were between 0 and
0.312% of one core; that resolution does not establish a precise CPU-performance difference.
The combined OSD had no active timer while idle.

These are offscreen measurements, not a guarantee about the playback device's compositor or GPU.
Repeat the comparison on the target device, using its actual graphical session:

```sh
python -m pip install psutil
python -m fs42.tools.diagnostics.display_resources --baseline-ref 4959e73 --seconds 30 --output runtime/display-resources.json
```

`psutil` is only an optional benchmark dependency. Add `--headless` for offscreen checks. The benchmark
exports the old source into a temporary directory, uses isolated status files, and cleans up its test
processes. It does not change the checkout or use the live player's status files. The baseline revision
must contain the previous OSD and `overlay/display` implementations.

## Existing installations

The field player now manages display startup, so the separate OSD unit is normally unnecessary:

```sh
systemctl --user disable --now fs42-osd
systemctl --user restart fs42
```

The optional standalone service remains available with `python -m fs42.tools.display.main`.
`python -m fs42.tools.osd.main` starts that same service for existing launchers. A single instance lock
prevents duplicate service windows. The standalone systemd template now restarts only on failure.

Runtime discovery and startup errors are stored under `runtime/display-service.json` and
`runtime/display-service.json.log`. The discovery file advertises a loopback-only socket and a private
startup-generated authentication token. The command API imports no Qt modules into its caller.
