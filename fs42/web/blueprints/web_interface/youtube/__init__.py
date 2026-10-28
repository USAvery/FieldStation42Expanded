# This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
"""Manage the YouTube channels available in the television On Demand menu."""
from fastapi import APIRouter, Request
from fs42.web.core import blueprint as bu

TITLE = 'YouTube'
MENU_GROUP = 'Console'
MENU_ORDER = 45
router = APIRouter()


@router.get('/youtube', name='youtube.index', include_in_schema=False)
def index(request: Request):
    """Render the channel management form and saved channel list."""
    return bu.render_page(request, __name__)
