#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
List and serve local media and JSON files through HTTP, including generated guide videos and audio
or video extension filtering.
"""
import os
import logging
import mimetypes

from fastapi import status
from fastapi import APIRouter
from fastapi import HTTPException
from fastapi.responses import FileResponse

from fs42.web.blueprints.api.media._constants import AUDIO_EXTENSIONS
from fs42.web.blueprints.api.media._constants import VIDEO_EXTENSIONS

router = APIRouter(prefix='/media', tags=['media'])
logger = logging.getLogger('media_api')

# Resolve the repository root above fs42/web/blueprints/api/media.
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..'))

GUIDE_VIDEOS_DIR = os.path.join(PROJECT_ROOT, 'runtime', 'guide_videos')


def safe_resolve(relative_path):
    """
    Resolve a requested path and reject resolved strings outside the project-root prefix

    :param relative_path: (str) requested path with leading separators removed
    :return:              (str) resolved filesystem path
    """
    clean = relative_path.lstrip('/').lstrip('\\')
    resolved = os.path.realpath(os.path.join(PROJECT_ROOT, clean))
    if not resolved.startswith(PROJECT_ROOT):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='invalid path')
    return resolved


@router.get('/list')
async def list_media(path: str, type: str = 'audio'):
    """
    List supported media files directly inside a requested project directory

    :param path: (str) project-relative directory to list
    :param type: (str) audio, video, or any
    :response:   (jsn) requested path and sorted media-serving URLs
    """
    resolved = safe_resolve(path)

    if not os.path.exists(resolved):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='path not found: {}'.format(path))
    if not os.path.isdir(resolved):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='path is not a directory')

    if type == 'video':
        allowed = VIDEO_EXTENSIONS
    elif type == 'any':
        allowed = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS
    else:
        allowed = AUDIO_EXTENSIONS

    try:
        files = sorted(f for f in os.listdir(resolved)
                       if os.path.isfile(os.path.join(resolved, f)) and os.path.splitext(f)[1].lower() in allowed)
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='permission denied')

    base = path.rstrip('/').rstrip('\\')
    urls = ['/media/file?path={0}/{1}'.format(base, f) for f in files]
    return {'path': path, 'files': urls}


@router.get('/file')
async def serve_file(path: str):
    """
    Serve a supported audio or video file after resolving and checking the requested path

    :param path: (str) requested project-relative media filename
    :return:     (FileResponse) file stream with its inferred media type
    """
    resolved = safe_resolve(path)

    if not os.path.exists(resolved):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='file not found')
    if not os.path.isfile(resolved):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='path is not a file')

    ext = os.path.splitext(resolved)[1].lower()
    if ext not in AUDIO_EXTENSIONS and ext not in VIDEO_EXTENSIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='unsupported file type')

    media_type, _ = mimetypes.guess_type(resolved)
    return FileResponse(resolved, media_type=media_type or 'application/octet-stream')


@router.get('/json')
async def serve_json(path: str):
    """
    Serve a JSON file after resolving its path and checking its extension

    :param path: (str) requested project-relative JSON filename
    :return:     (FileResponse) file stream with application/json content type
    """
    resolved = safe_resolve(path)

    if not os.path.exists(resolved):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='file not found')
    if not os.path.isfile(resolved):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='path is not a file')

    if os.path.splitext(resolved)[1].lower() != '.json':
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='unsupported file type')

    return FileResponse(resolved, media_type='application/json')


@router.get('/list_videos')
async def list_videos():
    """
    List supported guide-background videos as browser-accessible URLs

    :response: (jsn) sorted video URLs, or an empty list when the directory is absent
    """
    if not os.path.isdir(GUIDE_VIDEOS_DIR):
        return {'files': []}
    try:
        files = sorted(f for f in os.listdir(GUIDE_VIDEOS_DIR) if os.path.isfile(os.path.join(GUIDE_VIDEOS_DIR, f))
                       and os.path.splitext(f)[1].lower() in VIDEO_EXTENSIONS)
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='permission denied')
    return {'files': ['/guide_videos/{}'.format(f) for f in files]}
