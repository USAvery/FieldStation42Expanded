# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
"""Shared, validated control definitions; UI layouts and playback context remain separate."""
from dataclasses import dataclass
from functools import lru_cache
from types import MappingProxyType
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Arguments(BaseModel):
    model_config = ConfigDict(extra='forbid')


class ChannelArguments(Arguments):
    channel: int = Field(ge=0, strict=True)


class DigitArguments(Arguments):
    digit: str = Field(pattern=r'^[0-9]$')


class RelativeSeekArguments(Arguments):
    seconds: float = Field(ge=-86400, le=86400, allow_inf_nan=False)


class SeekArguments(Arguments):
    session_id: str = Field(min_length=1, max_length=64)
    position: float = Field(ge=0, allow_inf_nan=False)


class OverlayArguments(Arguments):
    session_id: str = Field(min_length=1, max_length=64)
    action: Literal['show', 'hide', 'hold']


@dataclass(frozen=True)
class Action:
    name: str
    label: str
    command: str = ''
    arguments: type[Arguments] = Arguments
    value: str = ''
    keys: tuple[str, ...] = ()
    service: str = ''

    def message(self, arguments):
        """Adapt a validated action to the existing player queue protocol."""
        values = self.arguments.model_validate(arguments).model_dump()
        message = {'command': self.command, **values}
        if self.value:
            message['key' if self.command == 'web_key' else 'action'] = self.value
        return message


_actions = [
    Action('navigation.up', 'UP', 'web_key', value='ArrowUp', keys=('ArrowUp',)),
    Action('navigation.down', 'DOWN', 'web_key', value='ArrowDown', keys=('ArrowDown',)),
    Action('navigation.left', 'LEFT', 'web_key', value='ArrowLeft', keys=('ArrowLeft',)),
    Action('navigation.right', 'RIGHT', 'web_key', value='ArrowRight', keys=('ArrowRight',)),
    Action('navigation.select', 'SELECT', 'web_key', value='Enter', keys=('Enter',)),
    Action('navigation.back', 'BACK', 'web_key', value='Escape', keys=('Escape', 'Backspace')),
    Action('navigation.page_previous', 'PREVIOUS', 'web_key', value='PageUp', keys=('PageUp',)),
    Action('navigation.page_next', 'NEXT', 'web_key', value='PageDown', keys=('PageDown',)),
    Action('navigation.home', 'HOME', 'web_key', value='Home', keys=('Home',)),
    Action('playback.play_pause', 'PLAY/PAUSE', 'mpv_command', value='play_pause', keys=(' ',)),
    Action('playback.seek_relative', 'SEEK', 'mpv_seek', RelativeSeekArguments),
    Action('playback.seek', 'SEEK', 'on_demand_seek', SeekArguments),
    Action('playback.controls', 'CONTROLS', 'on_demand_controls', OverlayArguments),
    Action('playback.subtitles', 'SUBTITLES', 'mpv_command', value='cycle_subtitles'),
    Action('playback.toggle_subtitles', 'SUBTITLES', 'mpv_command', value='toggle_subtitles'),
    Action('playback.audio', 'AUDIO', 'mpv_command', value='cycle_audio'),
    Action('menu.guide', 'GUIDE', 'guide'),
    Action('menu.on_demand', 'ON DEMAND', 'on_demand_menu'),
    Action('menu.close', 'CLOSE', 'menu_close'),
    Action('channel.next', 'CHANNEL UP', 'up'),
    Action('channel.previous', 'CHANNEL DOWN', 'down'),
    Action('channel.tune', 'CHANNEL', 'direct', ChannelArguments),
    Action('parental.digit', 'PIN', 'parental_digit', DigitArguments),
    Action('parental.clear', 'CLEAR', 'parental_clear'),
    Action('player.stop', 'STOPPING', 'exit'),
    Action('volume.up', 'VOL +', service='volume_up'),
    Action('volume.down', 'VOL -', service='volume_down'),
    Action('volume.mute', 'MUTE', service='volume_mute'),
]
ACTIONS = MappingProxyType({action.name: action for action in _actions})
KEY_ACTIONS = MappingProxyType({key: action.name for action in _actions for key in action.keys})
NAVIGATION_KEYS = frozenset(KEY_ACTIONS)
MPV_COMMANDS = MappingProxyType({
    'toggle_subtitles': ('cycle', 'sub-visibility'),
    'cycle_subtitles': ('cycle', 'sub'),
    'cycle_audio': ('cycle', 'audio'),
    'play_pause': ('cycle', 'pause'),
    # Compatibility for callers using the old fixed-step transport endpoints.
    'rewind': ('seek', -10, 'relative+exact'),
    'fast_forward': ('seek', 10, 'relative+exact'),
})


FILE_COMMANDS = frozenset(('up', 'down', 'direct', 'on_demand_menu'))


@lru_cache(maxsize=2)
def control_manifest(transport='queue'):
    """Expose action metadata and keyboard aliases without executable server internals."""
    return {'actions': {name: {'label': action.label, 'arguments': action.arguments.model_json_schema()}
                        for name, action in ACTIONS.items()
                        if transport != 'file' or action.command in FILE_COMMANDS}, 'keys': dict(KEY_ACTIONS)}
