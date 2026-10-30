# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
"""Publish bounded transport-overlay updates for one On Demand playback session."""
import math
import time
import uuid
from fs42.core import logger

_logger = logger.setup(__name__)


class OnDemandPlaybackControls:
    """Keep scrubbing scoped to the current video and leave MPV in full-screen playback."""

    def __init__(self, mpv, send, title, source, history=None, media_key=None):
        self.mpv = mpv
        self.send = send
        self.title = title
        self.source = source
        self.session_id = uuid.uuid4().hex
        self.ready = False
        self.suppressed = False
        self.visible_until = 0
        self.holding_until = 0
        self.next_update = 0
        self.last_visible = None
        self.history = history
        self.media_key = media_key
        self.next_checkpoint = 0
        self.last_position = None
        self.last_duration = 0

    def start(self):
        self.ready = True
        self.interact()
        self.tick(force=True)

    def interact(self, holding=False):
        self.suppressed = False
        self.visible_until = time.monotonic() + 4
        self.holding_until = time.monotonic() + 30 if holding else 0
        self.next_update = 0

    def hide(self):
        self.suppressed = True
        self.tick(force=True)

    def seek(self, session_id, position):
        """Ignore stale sessions and clamp a finite seek to the current video's duration."""
        if not self.ready or session_id != self.session_id:
            return False
        try:
            position = float(position)
            duration = float(self.mpv.duration or 0)
        except (TypeError, ValueError):
            return False
        if not math.isfinite(position) or not math.isfinite(duration) or duration <= 0:
            return False
        self.mpv.command('seek', max(0, min(position, duration)), 'absolute+exact')
        self.interact()
        return True

    def tick(self, menu_visible=False, force=False):
        """Update the visible bar four times per second; hidden bars do not poll timestamps."""
        now = time.monotonic()
        if not self.ready or (not force and now < self.next_update):
            return
        self.checkpoint()
        self.next_update = now + 0.25
        if menu_visible:
            return
        paused = bool(self.mpv.pause)
        buffering = bool(self.mpv.paused_for_cache)
        visible = not self.suppressed and (paused or buffering or now < max(self.visible_until, self.holding_until))
        if not force and not visible and self.last_visible is False:
            return
        self.last_visible = visible
        position = self.mpv.time_pos
        duration = self.mpv.duration
        self.send({'active': True, 'visible': visible, 'session_id': self.session_id,
                   'title': self.title, 'source': self.source, 'paused': paused,
                   'buffering': buffering,
                   'position': position if isinstance(position, (int, float)) and math.isfinite(position) else 0,
                   'duration': duration if isinstance(duration, (int, float)) and math.isfinite(duration) else 0})

    def checkpoint(self, force=False, completed=False):
        """Persist at most once every five seconds, including while the bar is hidden."""
        if not self.history or not self.ready or (not force and time.monotonic() < self.next_checkpoint):
            return
        self.next_checkpoint = time.monotonic() + 5
        try:
            if completed:
                self.history.save(self.media_key, 0, 0, completed=True)
                return
            position, duration = self.mpv.time_pos, self.mpv.duration
            if isinstance(position, (int, float)) and math.isfinite(position):
                self.last_position = position
            if isinstance(duration, (int, float)) and math.isfinite(duration):
                self.last_duration = duration
            if completed or self.last_position is not None:
                self.history.save(self.media_key, self.last_position or 0, self.last_duration, completed=completed)
        except Exception as error:
            _logger.warning('Could not save On Demand progress: {}'.format(error))

    def stop(self, menu_visible=False, completed=False):
        self.checkpoint(force=True, completed=completed)
        self.send({'active': False, 'visible': False, 'menu_visible': menu_visible})
        self.ready = False
