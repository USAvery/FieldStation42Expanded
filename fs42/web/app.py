#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Create and run the FastAPI station console with player command queues, configuration-error
responses, and a shutdown monitor tied to the server lifecycle.
"""
import asyncio
import logging
from queue import Empty
from contextlib import suppress
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from fs42.core import logger
from fs42.web.core import setup
from fs42.web.core.state import WebState
from fs42.core.station_manager import StationManager

_logger = logger.setup('fs42.web')


async def _monitor_shutdown(app):
    """
    Request a clean server shutdown when the parent player stops
    """
    while True:
        await asyncio.sleep(1)
        try:
            msg = app.state.shutdown_queue.get_nowait()
        except Empty:
            continue
        if msg == 'shutdown':
            app.state.server.should_exit = True
            return


@asynccontextmanager
async def _lifespan(app):
    """
    Own the shutdown monitor for the lifetime of the application
    """
    task = None
    if app.state.shutdown_queue is not None:
        task = asyncio.create_task(_monitor_shutdown(app))
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


def create_app(command_queue=None, shutdown_queue=None, server_conf=None):
    """
    Build the web console and register its API services

    :param command_queue:  (obj)  the queue used to send commands to the player
    :param shutdown_queue: (obj)  the parent player's shutdown queue
    :param server_conf:    (dict) optional server settings
    :return:              (obj)  the configured FastAPI application
    """
    app = FastAPI(title='FieldStation42 API', lifespan=_lifespan)
    app.state.player_command_queue = command_queue
    app.state.shutdown_queue = shutdown_queue
    app.state.web = WebState()
    conf = StationManager().server_conf if server_conf is None else server_conf
    setup.setup(app, conf)
    return app


class PlayerStatusFilter(logging.Filter):
    """
    Suppress routine player-status polling records from HTTP access logs
    """

    def filter(self, record):
        """
        Suppress frequent player status access messages
        """
        return '/player/status' not in record.getMessage()


def run_with_shutdown_queue(shutdown_queue, command_queue):
    """
    Run the web console with queues owned by the player
    """
    logging.getLogger('uvicorn.access').addFilter(PlayerStatusFilter())
    conf = StationManager().server_conf
    app = create_app(command_queue, shutdown_queue, server_conf=conf)
    server = uvicorn.Server(uvicorn.Config(app, host=conf['server_host'], port=conf['server_port']))
    app.state.server = server
    server.run()


def mount_fs42_api():
    """
    Run the standalone web console
    """
    run_with_shutdown_queue(None, None)


if __name__ == '__main__':
    mount_fs42_api()
