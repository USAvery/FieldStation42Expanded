#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Expose pay-per-view media listings, metadata, and artwork, and forward file-playback and key
commands to the player.
"""
import os
import logging
from fs42.core.controls import NAVIGATION_KEYS
import mimetypes
from typing import List
from typing import Optional

from fastapi import status
from fastapi import Request
from fastapi import APIRouter
from pydantic import BaseModel
from fastapi import HTTPException
from fastapi.responses import FileResponse

from fs42.tools.media import nfo_agent
from fs42.core.station_manager import StationManager
from fs42.web.core.tmdb_helper import get_tmdb_helper

router = APIRouter(prefix='/ppv', tags=['ppv'])


# Pydantic Models
class NFOData(BaseModel):
    """
    NFO file content: title, info line, description
    """
    title: str
    info: str
    description: str


class PPVContent(BaseModel):
    """
    A single PPV content item with video and metadata
    """
    filename: str
    video_path: str
    nfo: Optional[NFOData] = None
    has_nfo: bool
    has_image: bool
    image_url: Optional[str] = None


class PPVContentListResponse(BaseModel):
    """
    Response containing list of PPV content
    """
    channel_number: int
    network_name: str
    content_dir: str
    content_count: int
    contents: List[PPVContent]


class ErrorResponse(BaseModel):
    """
    Describe a failed pay-per-view API operation
    """
    success: bool = False
    error: str
    details: Optional[str] = None


class PlayFileRequest(BaseModel):
    """
    Request to play a file
    """
    file_path: str


class PlayFileResponse(BaseModel):
    """
    Response from play_file endpoint
    """
    success: bool
    message: str


# Endpoints


@router.get('/{channel_number}', response_model=PPVContentListResponse)
async def get_ppv_content(channel_number: int, variation: Optional[str] = None):
    """
    Get PPV content for a specific channel
    Reads the content_dir from the station config and returns all video files with their NFO metadata.

    :param channel_number: (obj) The channel number to get PPV content for
    :param variation: (obj) Optional variation parameter (for future use, similar to bump variations)
    """
    logger = logging.getLogger('PPV_API')

    # Get station configuration
    station_manager = StationManager()
    station = station_manager.station_by_channel(channel_number)

    if station is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail='Channel {} not found'.format(channel_number))

    # Get content_dir from station config
    content_dir = station.get('content_dir')
    if not content_dir:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail='Channel {} does not have a content_dir configured'.format(channel_number))

    # Check if content_dir exists
    if not os.path.exists(content_dir):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Content directory '{}' not found".format(content_dir))

    if not os.path.isdir(content_dir):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Content path '{}' is not a directory".format(content_dir))

    # Read directory contents
    try:
        contents = []
        video_extensions = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v'}

        for filename in sorted(os.listdir(content_dir)):
            file_path = os.path.join(content_dir, filename)

            # Skip directories
            if os.path.isdir(file_path):
                continue

            # Get file extension
            _, ext = os.path.splitext(filename)

            # Only process video files
            if ext.lower() in video_extensions:
                base_path = os.path.splitext(file_path)[0]
                base_name = os.path.splitext(filename)[0]

                # Look for corresponding NFO file
                nfo_data = None
                has_nfo = False

                file_meta = nfo_agent.read_metadata_from_disk(file_path)
                if file_meta:
                    fields = nfo_agent.display_fields(file_meta)
                    nfo_data = NFOData(
                        title=fields['title'],
                        info=fields['info'],
                        description=fields['description'],
                    )
                    has_nfo = True

                # Look for corresponding image file (jpg, jpeg, png)
                image_url = None
                has_image = False
                image_extensions = ['.jpg', '.jpeg', '.png']

                for img_ext in image_extensions:
                    img_path = base_path + img_ext
                    if os.path.exists(img_path):
                        # Create URL for image endpoint
                        image_url = '/ppv/image/{0}/{1}{2}'.format(channel_number, base_name, img_ext)
                        has_image = True
                        break

                # If no NFO or no image, try TMDB
                tmdb_data = None
                if not has_nfo or not has_image:
                    tmdb_helper = get_tmdb_helper()
                    if tmdb_helper.is_configured():
                        # Pass the raw filename - TMDB helper will parse year and normalize
                        tmdb_data = tmdb_helper.search_movie(base_name)

                # Use TMDB data if no NFO
                if not has_nfo:
                    if tmdb_data:
                        nfo_data = NFOData(
                            title=tmdb_data.get('title', base_name),
                            info=tmdb_data.get('release_date', '')[:4] if tmdb_data.get('release_date') else '',
                            description=tmdb_data.get('overview', ''))
                        logger.info('Using TMDB metadata for {}'.format(base_name))
                    else:
                        nfo_data = NFOData(title=base_name, info='', description='')

                # Use TMDB poster if no local image
                if not has_image and tmdb_data and tmdb_data.get('poster_url'):
                    image_url = tmdb_data['poster_url']
                    has_image = True
                    logger.info('Using TMDB poster for {}'.format(base_name))

                contents.append(
                    PPVContent(filename=filename, video_path=file_path, nfo=nfo_data, has_nfo=has_nfo,
                               has_image=has_image, image_url=image_url))

        return PPVContentListResponse(channel_number=channel_number,
                                      network_name=station.get('network_name', 'Unknown'), content_dir=content_dir,
                                      content_count=len(contents), contents=contents)

    except Exception as e:
        logger.error('Error reading content directory {0}: {1}'.format(content_dir, e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail='Failed to read content directory: {}'.format(str(e)))


@router.get('/image/{channel_number}/{filename}')
async def get_ppv_image(channel_number: int, filename: str):
    """
    Serve an image file from a channel's content_dir

    :param channel_number: (obj) The channel number
    :param filename: (obj) The image filename (e.g., "movie.jpg")
    """
    logger = logging.getLogger('PPV_API')

    # Get station configuration
    station_manager = StationManager()
    station = station_manager.station_by_channel(channel_number)

    if station is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail='Channel {} not found'.format(channel_number))

    # Get content_dir from station config
    content_dir = station.get('content_dir')
    if not content_dir:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail='Channel {} does not have a content_dir configured'.format(channel_number))

    # Security: Only allow image files
    allowed_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
    _, ext = os.path.splitext(filename)
    if ext.lower() not in allowed_extensions:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Only image files are allowed')

    # Security: Prevent directory traversal
    if '..' in filename or '/' in filename or '\\' in filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invalid filename')

    # Build full path
    image_path = os.path.join(content_dir, filename)

    # Check if file exists
    if not os.path.exists(image_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image '{}' not found".format(filename))

    # Check if it's a file (not a directory)
    if not os.path.isfile(image_path):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Path is not a file')

    # Determine media type
    media_type, _ = mimetypes.guess_type(image_path)
    if media_type is None:
        media_type = 'application/octet-stream'

    # Return the image file
    return FileResponse(
        image_path,
        media_type=media_type,
        headers={
            'Cache-Control': 'public, max-age=3600'  # Cache for 1 hour
        })


@router.post('/{channel_number}/play_file', response_model=PlayFileResponse)
async def play_file(channel_number: int, play_request: PlayFileRequest, request: Request):
    """
    Play a file by sending a command to the player via the command queue

    :param channel_number: (obj) The channel number (for validation)
    :param play_request: (obj) PlayFileRequest containing the file path
    :param request: (obj) FastAPI Request object (to access app state)
    """
    logger = logging.getLogger('PPV_API')

    # Get station configuration to validate channel exists
    station_manager = StationManager()
    station = station_manager.station_by_channel(channel_number)

    if station is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail='Channel {} not found'.format(channel_number))

    # Validate that the file exists
    if not os.path.exists(play_request.file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail='File not found: {}'.format(play_request.file_path))

    # Get the command queue from app state
    command_queue = request.app.state.player_command_queue

    # Create the command to send to the player
    command = {'command': 'play_file', 'file_path': play_request.file_path}

    try:
        logger.info('Sending play command for file: {}'.format(play_request.file_path))

        # Put the command in the queue
        command_queue.put(command)

        logger.info('Successfully queued play command for: {}'.format(play_request.file_path))

        return PlayFileResponse(
            success=True, message='Play command sent for: {}'.format(os.path.basename(play_request.file_path)))

    except Exception as e:
        logger.error('Error sending play command: {}'.format(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail='Failed to send play command: {}'.format(str(e)))


@router.post('/{channel_number}/key/{key_name}')
async def send_key(channel_number: int, key_name: str, request: Request):
    """
    Send a keypress to the PPV web channel
    """
    allowed_keys = NAVIGATION_KEYS
    if key_name not in allowed_keys:
        raise HTTPException(status_code=400, detail='Key must be one of: {}'.format(allowed_keys))
    command_queue = request.app.state.player_command_queue
    try:
        command_queue.put({'command': 'web_key', 'key': key_name})
        return {'success': True, 'key': key_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
