# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
"""Manage saved YouTube channels and browse their recent uploads."""
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field
from fs42.tools.on_demand.youtube import YouTubeLibrary, YouTubeError
from fs42.tools.on_demand.progress import PlaybackOptions

router = APIRouter(prefix='/on-demand/youtube', tags=['youtube'])


class ChannelRequest(BaseModel):
    """Accept a channel URL, handle, or canonical channel ID."""
    url: str = Field(min_length=1, max_length=500)


def _call(action, *args, missing=False):
    try:
        return action(*args)
    except ValueError as error:
        raise HTTPException(status_code=404 if missing else 400, detail=str(error)) from error
    except YouTubeError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.get('/channels')
def get_channels():
    """List the saved channels for both the console and television menu."""
    return {'channels': YouTubeLibrary().get_channels()}


@router.post('/channels')
def add_channel(payload: ChannelRequest):
    """Resolve a channel and persist its canonical identity."""
    return _call(YouTubeLibrary().add_channel, payload.url)


@router.delete('/channels/{channel_id}')
def remove_channel(channel_id: str):
    """Remove a saved channel and its cached uploads."""
    _call(YouTubeLibrary().remove_channel, channel_id, missing=True)
    return {'success': True}


@router.get('/channels/{channel_id}/uploads')
def get_uploads(channel_id: str, page: int = Query(0, ge=0)):
    """Return one page from the channel's latest public uploads."""
    return _call(YouTubeLibrary().get_uploads, channel_id, page, missing=True)


@router.post('/channels/{channel_id}/play/{video_id}')
def play_upload(channel_id: str, video_id: str, request: Request, options: PlaybackOptions | None = None):
    """Queue a single upload only after validating its saved-channel membership."""
    queue = request.app.state.player_command_queue
    if queue is None:
        raise HTTPException(status_code=503, detail='The player is not connected. Start FieldStation42 and retry.')
    _call(YouTubeLibrary().get_selection, channel_id, video_id, missing=True)
    queue.put({'command': 'on_demand', 'entry_id': {'source': 'youtube', 'channel_id': channel_id, 'video_id': video_id,
                                                'start_over': (options or PlaybackOptions()).start_over}})
    return {'success': True}
