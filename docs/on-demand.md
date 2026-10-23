# On Demand

Press the dedicated **On Demand** button on the web remote to open the menu directly on the TV.
The remote switches to directional navigation. The physical controller exposes a configurable
`show_on_demand` action, mapped to **O** by default; assign it to the remote's On Demand key in
`runtime/remote_controller.json`. The menu is also available at `/on-demand` on the player web server.

The menu uses the Comcast logo, blue two-column choices, yellow selection, and the existing
native channel preview. Arrows move between choices; Enter opens the selection. Use Back,
Escape, or Page Up to return. The TV Listings button returns to the guide.

Movies and episodes come from active stations' local video catalogs. Commercials, bumps, audio,
streams, and duplicate references to the same file are excluded. Title results are paginated;
the menu reads the catalog and cached metadata instead of scanning directories or probing files.

- **Top Picks** lists frequently scheduled titles using the catalog's existing play counts.
- **Movies** and **TV Shows** use cached metadata; episode filenames are recognized when metadata
  is missing. Unclassified feature videos appear under Movies and All Titles.
- **Kids** uses genre and catalog tags such as kids, children, family, animation, and cartoon.
- **Recently Added** uses catalog insertion order.
- **Short Features** includes titles under 30 minutes; **Long Features** includes titles of at least
  90 minutes.
- **By Channel** browses one station's catalog. **All Titles** browses the complete available library.
- **Search** accepts a typed title or the on-screen keyboard. Searches run when submitted.

Selecting a title opens its description and a Play button. Playback is resolved by catalog ID,
revalidated against the active station, and checked for local file availability. A protected source
station uses the existing PIN prompt. The existing MPV instance plays the selection once without
changing the tuned channel. At completion the menu returns and normal channel scheduling resumes
underneath it. Channel commands can interrupt playback.

There is no browser media player, background music, slideshow, directory scan, or library polling.
The preview rectangle remains transparent for the native MPV surface. Opening this page in a normal
browser shows an empty preview rather than starting a second video stream.
