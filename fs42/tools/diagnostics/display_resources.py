#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Compare the shared display service with its predecessor using isolated windows and runtime files
"""
import os
import io
import sys
import json
import time
import queue
import zipfile
import argparse
import tempfile
import subprocess

from fs42.core.paths import PROJECT_ROOT


def _run_baseline(kind, baseline_dir, config, database):
    """
    Run one pre-service display using exported source and isolated runtime inputs

    :param kind:         (str) osd, now_playing, parental_controls, or ticker
    :param baseline_dir: (str) exported fs42/tools directory containing the previous implementations
    :param config:       (str) isolated OSD configuration filename
    :param database:     (str) isolated metadata database filename
    """
    import fs42.tools
    fs42.tools.__path__.insert(0, baseline_dir)
    from PySide6.QtWidgets import QApplication
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    if kind == 'osd':
        from fs42.tools.osd import _api
        from fs42.tools.osd.osd import OsdWindow
        _api.CONFIG_FILE_PATH = config
        window = OsdWindow(_api.load_objects())
    elif kind == 'now_playing':
        from fs42.tools.overlay.display.now_playing_display import NowPlayingDisplay
        window = NowPlayingDisplay('Track.mp3', database)
        window.show()
    elif kind == 'ticker':
        from fs42.tools.overlay.display.ticker_display import TickerDisplay
        window = TickerDisplay('Display service resource comparison', iterations=10000)
        window.show()
    else:
        from fs42.tools.overlay.display.parental_controls_display import ParentalControlsDisplay
        window = ParentalControlsDisplay('Station', queue.Queue())
        window.show()
    app.exec()


def _sample(pids, seconds):
    """
    Measure aggregate CPU and memory across complete display subprocess trees

    Include virtual-environment launcher children on Windows. CPU is expressed as
    a percentage of one core; short samples can fall below the platform's resolution.

    :param pids:    (list) root display-process identifiers
    :param seconds: (float) CPU sampling duration
    :return:        (dict) operating-system process count, resident/private memory, and CPU usage
    """
    try:
        import psutil
    except ImportError:
        raise SystemExit('Install the optional benchmark dependency with: python -m pip install psutil')
    processes = {}
    for pid in pids:
        root = psutil.Process(pid)
        for process in [root] + root.children(recursive=True):
            processes[process.pid] = process
    start = sum(sum(process.cpu_times()[:2]) for process in processes.values())
    started = time.monotonic()
    time.sleep(seconds)
    elapsed = time.monotonic() - started
    used = sum(sum(process.cpu_times()[:2]) for process in processes.values()) - start
    return {'os_processes': len(processes),
            'rss_mib': round(sum(process.memory_info().rss for process in processes.values()) / 1048576, 2),
            'private_mib': round(sum(process.memory_full_info().uss
                                     for process in processes.values()) / 1048576, 2),
            'cpu_percent_one_core': round(used / elapsed * 100, 3)}


def _export_baseline(ref, directory):
    """
    Export the prior display packages into temporary storage without changing the checkout
    """
    archive = subprocess.check_output(['git', 'archive', '--format=zip', ref, 'fs42/tools/osd',
                                       'fs42/tools/overlay'], cwd=PROJECT_ROOT)
    with zipfile.ZipFile(io.BytesIO(archive)) as source:
        source.extractall(directory)
    return os.path.join(directory, 'fs42', 'tools')


def _measure_baseline(directory, config, database, seconds, environment):
    """
    Compare the prior OSD alone with the OSD and three concurrently active overlay processes
    """
    processes = []
    try:
        for kind in ('osd', 'now_playing', 'parental_controls', 'ticker'):
            command = [sys.executable, '-m', 'fs42.tools.diagnostics.display_resources', '--worker', kind,
                       '--baseline-dir', directory, '--config', config, '--database', database]
            process = subprocess.Popen(command, cwd=PROJECT_ROOT, env=environment,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            processes.append(process)
            time.sleep(1.5)
            if any(process.poll() is not None for process in processes):
                msg = 'A baseline display failed; select a commit containing the prior display classes'
                raise RuntimeError(msg)
            if kind == 'osd':
                idle = _sample([process.pid], seconds)
        active = _sample([process.pid for process in processes], seconds)
        return {'idle': idle, 'active': active}
    finally:
        import psutil
        descendants = []
        for process in processes:
            try:
                descendants.extend(psutil.Process(process.pid).children(recursive=True))
            except psutil.NoSuchProcess:
                pass
        for child in descendants:
            try:
                child.terminate()
            except psutil.NoSuchProcess:
                pass
        for process in processes:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=5)
        _, remaining = psutil.wait_procs(descendants, timeout=3)
        for child in remaining:
            child.kill()


def _measure_service(directory, config, database, seconds):
    """
    Measure the combined service before, during, and after showing the same three overlays
    """
    from fs42.tools.display.client import DisplayClient
    client = DisplayClient(os.path.join(directory, 'display.json'), config).connect()
    try:
        pid = client._process.pid
        result = {'idle': _sample([pid], seconds)}
        panels = [client.show('now_playing', file_path='Track.mp3', db_path=database),
                  client.show('parental_controls', network_name='Station'),
                  client.show('ticker', text='Display service resource comparison', iterations=10000)]
        time.sleep(0.3)
        result['active'] = _sample([pid], seconds)
        for panel in panels:
            panel.hide()
        time.sleep(0.3)
        result['idle_after_active'] = _sample([pid], seconds)
        result['idle_osd_timer_active'] = client.request('inspect')['osd_timer_active']
        return result
    finally:
        client.close()


def main():
    """
    Compare the shared service with an earlier Git revision on the current display hardware
    """
    parser = argparse.ArgumentParser(description='Compare display CPU and memory with the prior process layout')
    parser.add_argument('--baseline-ref', help='Git revision before the shared service, such as 4959e73')
    parser.add_argument('--seconds', type=float, default=10, help='Sampling seconds for each state')
    parser.add_argument('--headless', action='store_true',
                        help='Use offscreen Qt instead of the actual compositor')
    parser.add_argument('--output', help='Optional JSON results filename')
    parser.add_argument('--worker', choices=['osd', 'now_playing', 'parental_controls', 'ticker'],
                        help=argparse.SUPPRESS)
    parser.add_argument('--baseline-dir', help=argparse.SUPPRESS)
    parser.add_argument('--config', help=argparse.SUPPRESS)
    parser.add_argument('--database', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        return _run_baseline(args.worker, args.baseline_dir, args.config, args.database)
    if not args.baseline_ref or args.seconds <= 0:
        parser.error('--baseline-ref and a positive --seconds value are required')
    try:
        import psutil
    except ImportError:
        parser.error('Install the optional benchmark dependency with: python -m pip install psutil')
    if args.headless:
        os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    with tempfile.TemporaryDirectory() as directory:
        baseline = _export_baseline(args.baseline_ref, directory)
        config = os.path.join(directory, 'osd.json')
        database = os.path.join(directory, 'metadata.db')
        with open(config, 'w') as f_out:
            json.dump([{'socket_file': os.path.join(directory, 'status.json')},
                       {'type': 'VolumeDisplay', 'socket_file': os.path.join(directory, 'volume.json')}], f_out)
        result = {'baseline_ref': args.baseline_ref, 'headless': args.headless, 'sample_seconds': args.seconds,
                  'baseline': _measure_baseline(baseline, config, database, args.seconds, dict(os.environ)),
                  'combined': _measure_service(directory, config, database, args.seconds)}
        print(json.dumps(result, indent=2))
        if args.output:
            with open(args.output, 'w') as f_out:
                json.dump(result, f_out, indent=2)


if __name__ == '__main__':
    main()
