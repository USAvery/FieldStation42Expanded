#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Start background catalog and schedule builds through HTTP endpoints and expose task progress stored
on the application instance.
"""
import uuid
import threading
import traceback

from fastapi import Request
from fastapi import APIRouter

from fs42.tools.catalog import catalog_api
from fs42.tools.catalog.catalog import ShowCatalog
from fs42.core.station_manager import StationManager
from fs42.tools.catalog import catalog as catalog_utils
from fs42.tools.schedule.liquid_manager import LiquidManager
from fs42.tools.schedule.liquid_schedule import LiquidSchedule

router = APIRouter(prefix='/build', tags=['build'])

# Global dicts and locks for task tracking


@router.post('/catalog/{network_name}')
async def rebuild_catalog(network_name: str, request: Request):
    """
    Start a background catalog rebuild and discard affected station schedules

    :param network_name: (str) network to rebuild, or all for every station
    :param request:      (Request) request providing application task state and player queues
    :response:           (jsn) task identifier used to poll progress
    """
    task_id = str(uuid.uuid4())
    with request.app.state.web.rebuild_tasks_lock:
        request.app.state.web.rebuild_tasks[task_id] = {'status': 'starting', 'log': ''}

    def rebuild_worker():
        """
        Reset affected schedules, rebuild catalog data, and record background task progress
        """
        # Clear the fluid file cache dedup set so scan_file_cache runs fresh
        # for each unique content_dir in this rebuild pass.  Without this, a
        # second rebuild request in the same server process would silently skip
        # all directory scans, missing any files added since the first request.
        catalog_utils.clear_fluid_cache()
        try:
            with request.app.state.web.rebuild_tasks_lock:
                request.app.state.web.rebuild_tasks[task_id]['status'] = 'running'
                request.app.state.web.rebuild_tasks[task_id]['log'] += 'Starting catalog rebuild for {}\n'.format(
                    network_name)

            to_rebuild = []
            if not network_name or network_name == 'all':
                to_rebuild = StationManager().stations
            else:
                to_rebuild = [StationManager().station_by_name(network_name)]

            for station in to_rebuild:
                if station['_has_schedule']:
                    with request.app.state.web.rebuild_tasks_lock:
                        request.app.state.web.rebuild_tasks[task_id]['log'] += 'Deleting schedule for {}\n'.format(
                            station['network_name'])
                        LiquidManager().reset_schedule(station)
                    with request.app.state.web.rebuild_tasks_lock:
                        request.app.state.web.rebuild_tasks[task_id][
                            'log'] += 'Deleted schedule {} - rebuilding catalog now.\n'.format(
                                station['network_name'])
                if station['_has_catalog']:
                    catalog_api.delete_catalog(station)
                    ShowCatalog(station, rebuild_catalog=True)
                    with request.app.state.web.rebuild_tasks_lock:
                        request.app.state.web.rebuild_tasks[task_id]['log'] += 'Rebuilt catalog for {}\n'.format(
                            station['network_name'])

            with request.app.state.web.rebuild_tasks_lock:
                request.app.state.web.rebuild_tasks[task_id]['status'] = 'done'
                request.app.state.web.rebuild_tasks[task_id]['log'] += "Catalog rebuild complete.\n"
                request.app.state.web.rebuild_tasks[task_id]['log'] += "Reloading data and state.\n"
                command_queue = request.app.state.player_command_queue
                if command_queue:
                    command_queue.put({'command': 'reload_data'})
                #else:
                LiquidManager().reload_schedules()

        except Exception as e:
            with request.app.state.web.rebuild_tasks_lock:
                request.app.state.web.rebuild_tasks[task_id]['status'] = 'error'
                request.app.state.web.rebuild_tasks[task_id][
                    'log'] += 'Error: {0}\n\nDetailed Error Message:\n{1}'.format(e, traceback.format_exc())

    thread = threading.Thread(target=rebuild_worker, daemon=True)
    thread.start()
    return {'task_id': task_id}


@router.get('/catalog/status/{task_id}')
async def rebuild_catalog_status(task_id: str, request: Request):
    """
    Return a catalog rebuild's current status and accumulated log

    :param task_id: (str) identifier returned when the rebuild was started
    :param request: (Request) request providing application task state
    :response:      (jsn) status and log, or an unknown-task error
    """
    with request.app.state.web.rebuild_tasks_lock:
        task = request.app.state.web.rebuild_tasks.get(task_id)
        if not task:
            return {'error': 'Task ID not found.'}
        return {'status': task['status'], 'log': task['log']}


@router.post('/schedule/add_time/{amount}/{network_name}')
async def add_time_to_schedule(amount: str, network_name: str, request: Request):
    """
    Start a background extension of one or all station schedules

    :param amount:       (str) extension unit accepted by the schedule builder
    :param network_name: (str) network to extend, or all
    :param request:      (Request) request providing task state and player queues
    :response:           (jsn) task identifier used to poll progress
    """
    task_id = str(uuid.uuid4())
    with request.app.state.web.add_time_tasks_lock:
        request.app.state.web.add_time_tasks[task_id] = {'status': 'starting', 'log': ''}

    def add_time_worker():
        """
        Extend selected schedules, log progress, and reload scheduling state after completion
        """
        try:
            with request.app.state.web.add_time_tasks_lock:
                request.app.state.web.add_time_tasks[task_id]['status'] = 'running'

            # Determine which stations to process
            to_process = []
            if not network_name or network_name == 'all':
                to_process = StationManager().stations
            else:
                to_process = [StationManager().station_by_name(network_name)]

            for station in to_process:
                if station['_has_schedule']:
                    with request.app.state.web.add_time_tasks_lock:
                        request.app.state.web.add_time_tasks[task_id][
                            'log'] += 'Adding {0} to schedule for {1}\n'.format(amount, station['network_name'])
                    liquid = LiquidSchedule(station)
                    liquid.add_amount(amount)

            with request.app.state.web.add_time_tasks_lock:
                request.app.state.web.add_time_tasks[task_id]['status'] = 'done'
                request.app.state.web.add_time_tasks[task_id]['log'] += "Add time to schedule complete.\n"
                request.app.state.web.add_time_tasks[task_id]['log'] += "Reloading data and state.\n"
                command_queue = request.app.state.player_command_queue
                if command_queue:
                    command_queue.put({'command': 'reload_data'})

                LiquidManager().reload_schedules()
        except Exception as e:
            with request.app.state.web.add_time_tasks_lock:
                request.app.state.web.add_time_tasks[task_id]['status'] = 'error'
                request.app.state.web.add_time_tasks[task_id][
                    'log'] += 'Error: {0}\n\nDetailed Error Message:\n{1}'.format(e, traceback.format_exc())

    thread = threading.Thread(target=add_time_worker, daemon=True)
    thread.start()
    return {'task_id': task_id}


@router.get('/schedule/add_time/status/{task_id}')
async def add_time_to_schedule_status(task_id: str, request: Request):
    """
    Return a schedule extension's current status and accumulated log

    :param task_id: (str) background extension identifier
    :param request: (Request) request providing application task state
    :response:      (jsn) status and log, or an unknown-task error
    """
    with request.app.state.web.add_time_tasks_lock:
        task = request.app.state.web.add_time_tasks.get(task_id)
        if not task:
            return {'error': 'Task ID not found.'}
        return {'status': task['status'], 'log': task['log']}


@router.post('/schedule/reset/{network_name}')
async def rebuild_schedule(network_name: str, request: Request):
    """
    Start a background schedule reset for one network or all networks

    This operation deletes saved programming and rewinds pending sequences; it does
    not generate replacement programming.

    :param network_name: (str) network to reset, or all
    :param request:      (Request) request providing task state and player queues
    :response:           (jsn) task identifier used to poll progress
    """
    task_id = str(uuid.uuid4())
    with request.app.state.web.rebuild_tasks_lock:
        request.app.state.web.rebuild_tasks[task_id] = {'status': 'starting', 'log': ''}

    def rebuild_schedule_worker():
        """
        Reset selected schedules and notify the player to reload its scheduling state
        """
        try:
            with request.app.state.web.rebuild_tasks_lock:
                request.app.state.web.rebuild_tasks[task_id]['status'] = 'running'
                request.app.state.web.rebuild_tasks[task_id]['log'] += 'Starting schedule rebuild for {}\n'.format(
                    network_name)

            to_rebuild = []
            if not network_name or network_name == 'all':
                to_rebuild = StationManager().stations
            else:
                to_rebuild = [StationManager().station_by_name(network_name)]

            for station in to_rebuild:
                if station['_has_schedule']:
                    LiquidManager().reset_schedule(station)
                    with request.app.state.web.rebuild_tasks_lock:
                        request.app.state.web.rebuild_tasks[task_id]['log'] += 'Rebuilt schedule for {}\n'.format(
                            station['network_name'])

            with request.app.state.web.rebuild_tasks_lock:
                request.app.state.web.rebuild_tasks[task_id]['status'] = 'done'
                request.app.state.web.rebuild_tasks[task_id]['log'] += "Schedule rebuild complete.\n"
                request.app.state.web.rebuild_tasks[task_id]['log'] += "Reloading data and state.\n"
                command_queue = request.app.state.player_command_queue
                if command_queue:
                    command_queue.put({'command': 'reload_data'})
                else:
                    LiquidManager().reload_schedules()
        except Exception as e:
            with request.app.state.web.rebuild_tasks_lock:
                request.app.state.web.rebuild_tasks[task_id]['status'] = 'error'
                request.app.state.web.rebuild_tasks[task_id][
                    'log'] += 'Error: {0}\n\nDetailed Error Message:\n{1}'.format(e, traceback.format_exc())

    thread = threading.Thread(target=rebuild_schedule_worker, daemon=True)
    thread.start()
    return {'task_id': task_id}


@router.get('/schedule/reset/status/{task_id}')
async def rebuild_schedule_status(task_id: str, request: Request):
    """
    Return a schedule reset's current status and accumulated log

    :param task_id: (str) background reset identifier
    :param request: (Request) request providing application task state
    :response:      (jsn) status and log, or an unknown-task error
    """
    with request.app.state.web.rebuild_tasks_lock:
        task = request.app.state.web.rebuild_tasks.get(task_id)
        if not task:
            return {'error': 'Task ID not found.'}
        return {'status': task['status'], 'log': task['log']}
