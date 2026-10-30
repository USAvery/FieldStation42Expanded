# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
"""Route runtime input by playback context, independently of HTTP and UI layouts."""
from fs42.core.controls import NAVIGATION_KEYS, RelativeSeekArguments
from fs42.tools.field_player._constants import PlayerState


class RuntimeControlRouter:
    """Keep legacy protocol decoding at one boundary and dispatch normalized commands."""

    LEGACY_ACTIONS = {'guide_toggle': 'guide', 'on_demand_menu': 'on_demand_menu', 'menu_close': 'menu_close', 'parental_clear': 'parental_clear'}

    def __init__(self, player):
        self.player = player
        self.handlers = {
            'guide': lambda command: player._toggle_guide_overlay(),
            'on_demand_menu': lambda command: player._toggle_on_demand_overlay(),
            'menu_close': self.close_menu,
            'mpv_command': self.mpv_command,
            'mpv_seek': self.relative_seek,
            'on_demand_seek': self.timeline_seek,
            'on_demand_controls': self.overlay,
            'web_key': self.navigation,
        }

    @property
    def playback(self):
        return getattr(self.player, '_on_demand_controls', None)

    @classmethod
    def decode(cls, payload):
        if isinstance(payload, dict):
            return payload
        if isinstance(payload, str):
            if payload in cls.LEGACY_ACTIONS:
                return {'command': cls.LEGACY_ACTIONS[payload]}
            kind, separator, value = payload.partition(':')
            if separator and kind in ('mpv_command', 'web_key', 'parental_digit'):
                field = {'mpv_command':'action', 'web_key':'key', 'parental_digit':'digit'}[kind]
                return {'command': kind, field: value}
        return {}

    def dispatch(self, response):
        if not response or response.status != PlayerState.SUCCESS:
            return False
        command = self.decode(response.payload)
        handler = self.handlers.get(command.get('command'))
        if handler is None:
            return False
        # Resolve focus at execution time; clients do not need to know which page is visible.
        try:
            if command['command'] == 'web_key':
                return self.navigation(command)
            handler(command)
        except Exception as error:
            self.player._l.warning('Control {} failed: {}'.format(command['command'], error))
        return True

    def close_menu(self, command):
        if self.player.guide_visible:
            self.player._close_guide_overlay()

    def mpv_command(self, command):
        self.player.mpv_runtime_command(command.get('action'))

    def relative_seek(self, command):
        seconds = RelativeSeekArguments.model_validate({'seconds': command.get('seconds')}).seconds
        self.player.mpv.command('seek', seconds, 'relative+exact')
        if self.playback:
            self.playback.interact()
            self.player._tick_on_demand_controls(force=True)

    def timeline_seek(self, command):
        if self.playback:
            self.playback.seek(command.get('session_id'), command.get('position'))

    def overlay(self, command):
        if not self.playback or command.get('session_id') != self.playback.session_id:
            return
        action = command.get('action')
        if action == 'hide':
            self.playback.hide()
        elif action in ('show', 'hold'):
            self.playback.interact(holding=action == 'hold')
            self.player._tick_on_demand_controls(force=True)

    def navigation(self, command):
        key = command.get('key')
        if key not in NAVIGATION_KEYS:
            return True
        player = self.player
        if self.playback and not player.guide_visible:
            if key in ('Escape', 'Backspace'):
                self.playback.hide()
            else:
                self.playback.interact()
                player._tick_on_demand_controls(force=True)
                key = {'PageUp': 'ArrowUp', 'PageDown': 'ArrowDown'}.get(key, key)
                if player.guide_queue:
                    player.guide_queue.put('key:' + key)
            return True
        if player.guide_visible and player.guide_process and player.guide_process.is_alive() and player.guide_queue:
            player.guide_queue.put('key:' + key)
            return True
        process = getattr(player, 'web_process', None)
        web_queue = getattr(player, 'web_queue', None)
        if process and process.is_alive() and web_queue:
            web_queue.put('key:' + key)
            return True
        return False
