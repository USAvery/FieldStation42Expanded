#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Log server failures and present consistent HTML or JSON error responses.
"""
import logging
import traceback
from http import HTTPStatus

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException

from fs42.web.core import _constants
from fs42.core.station_manager import StationConfigError

_logger = logging.getLogger('fs42.web.errors')
_templates = Jinja2Templates(directory=_constants.WEB_DIR + '/templates')


def respond(request, status, detail, headers=None, details=None):
    """
    Render errors for page requests and retain JSON error details for API clients
    """
    route = request.scope.get('route')
    api = getattr(route, 'include_in_schema', False)
    accept = request.headers.get('accept', '')
    if 'text/html' not in accept or api:
        return JSONResponse(status_code=status, content={'detail': jsonable_encoder(detail)}, headers=headers)
    return _templates.TemplateResponse(request=request, name='error.html', status_code=status, headers=headers,
                                       context=dict(code=status, title=HTTPStatus(status).phrase,
                                                    message=detail, details=details))


async def handle_http_error(request: Request, error: HTTPException):
    """
    Keep HTTP status codes, validation detail, and required response headers
    """
    return respond(request, error.status_code, error.detail, error.headers)


async def handle_validation_error(request: Request, error: RequestValidationError):
    """
    Preserve FastAPI's structured request-validation response
    """
    return respond(request, 422, error.errors())


async def handle_exception(request: Request, error: Exception):
    """
    Log the traceback and keep unexpected failure details out of normal responses
    """
    _logger.error('Unhandled error at %s %s', request.method, request.url.path,
                  exc_info=(type(error), error, error.__traceback__))
    debug = request.app.state.web_settings.get('debug', False)
    details = ''.join(traceback.format_exception(type(error), error, error.__traceback__)) if debug else None
    return respond(request, 500, 'An unexpected error occurred.', details=details)


async def handle_station_error(request: Request, error: StationConfigError):
    """
    Explain station configuration failures using the common error presentation
    """
    _logger.error('Station configuration error: %s', error)
    return respond(request, 500, str(error))


def setup(app):
    """
    Install shared handlers without enabling framework traceback responses
    """
    app.add_exception_handler(HTTPException, handle_http_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(StationConfigError, handle_station_error)
    app.add_exception_handler(Exception, handle_exception)
