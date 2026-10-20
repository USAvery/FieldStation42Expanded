#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Build station options and define administration errors
"""
import argparse


def build_parser():
    """
    Build parser
    """
    parser = argparse.ArgumentParser(description='FieldStation42 Catalog and Liquid-Schedule Generation')
    parser.add_argument(
        '-g',
        '--graphical_interface',
        action='store_true',
        help='Run graphical interface to configure catalogs and schedules',
    )
    parser.add_argument('-l', '--logfile', help='Set logging to use output file - will append each run')
    parser.add_argument(
        '-c',
        '--check_catalogs',
        nargs='*',
        help='Check catalogs for the specified network names, print report and exit.',
    )
    parser.add_argument(
        '-p',
        '--printcat',
        help='Print the catalog for the specified network name and exit',
    )
    parser.add_argument(
        '-r',
        '--rebuild_catalog',
        nargs='*',
        help='Rebuild catalog for the specified network names or all networks if no parameter given',
    )
    parser.add_argument(
        '-q',
        '--rebuild_sequences',
        nargs='*',
        help=
        'Restarts sequences for the named stations or all stations if none are specified. This will take effect in next schedule build.',
    )
    parser.add_argument(
        '-a',
        '--scan_sequences',
        nargs='*',
        help='Scan for new sequences that have been added to configurations for next schedule build.',
    )
    parser.add_argument(
        '-b',
        '--break_detect_dir',
        help='Scan for points break insertion point in media files in the provided directory. (VERY experimental)',
    )
    parser.add_argument(
        '-t',
        '--chapter_detect_dir',
        help='Scan for chapter markers in media files in the provided directory.',
    )
    parser.add_argument(
        '-w',
        '--add_week',
        nargs='*',
        help='Add one week to the specified stations, or all stations if none are specified.',
    )
    parser.add_argument(
        '-m',
        '--add_month',
        nargs='*',
        help='Add one month to the specified stations, or all stations if none are specified.',
    )
    parser.add_argument(
        '-d',
        '--add_day',
        nargs='*',
        help='Add one day to to the specified stations, or all stations if none are specified.',
    )
    parser.add_argument(
        '-e',
        '--schedule',
        action='store_true',
        help='View schedule summary information for all stations.',
    )
    parser.add_argument(
        '-u',
        '--print_schedule',
        help='Print schedule for current day for the specified network name',
    )
    parser.add_argument(
        '-x',
        '--delete_schedules',
        nargs='*',
        help='Delete the schedule for the specified network names or all networks if no parameter given',
    )
    parser.add_argument(
        '-f',
        '--force',
        action='store_true',
        help=
        "With -r or -x will force deletion of schedules and catalogs if they are failing. Won't reset sequences, file cache or breakpoints",
    )
    parser.add_argument(
        '--skip_chapter_scan',
        action='store_true',
        help='Skip automatic chapter scanning during catalog rebuild',
    )
    parser.add_argument(
        '--reset_chapters',
        action='store_true',
        help='Clear all cached chapter markers from the database',
    )
    parser.add_argument(
        '--reset_breaks',
        action='store_true',
        help='Clear all cached break points from the database',
    )
    parser.add_argument(
        '-v',
        '--verbose',
        action='store_true',
        help='Set logging verbosity level to very chatty',
    )
    parser.add_argument(
        '-s',
        '--server',
        action='store_true',
        help='Run the FieldStation42 web API server after other actions.',
    )

    parser.add_argument('--limit_memory', nargs=1, type=float,
                        help='Enter a number 0.1 and 1.0 to limit the memory usage of a command.')

    return parser


class StationError(Exception):
    pass


def get_available_memory():
    """
    Get available Linux memory in KiB
    """
    with open('/proc/meminfo', 'r') as f_in:
        return sum(int(line.split()[1]) for line in f_in if line.split()[0] in ('MemFree:', 'Buffers:', 'Cached:'))
