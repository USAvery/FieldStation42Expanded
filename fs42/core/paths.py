#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Manage paths
"""
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def split_parts(path):
    """
    Split a filesystem path into its anchor and lexical components
    """
    value = os.fspath(path)
    if os.path.altsep:
        value = value.replace(os.path.altsep, os.path.sep)
    drive, tail = os.path.splitdrive(value)
    anchor = drive + os.path.sep if tail.startswith(os.path.sep) else drive
    parts = tuple(part for part in tail.split(os.path.sep) if part and part != '.')
    return (anchor, ) + parts if anchor else parts


def get_relative_path(path, directory):
    """
    Get a lexical relative path, or None when outside the directory
    """
    parts = split_parts(path)
    base_parts = split_parts(directory)
    prefix = tuple(os.path.normcase(part) for part in parts[:len(base_parts)])
    base = tuple(os.path.normcase(part) for part in base_parts)
    if prefix != base:
        return None
    return os.path.join(*parts[len(base_parts):]) if len(parts) > len(base_parts) else '.'


def read_text(path):
    """
    Read text using the platform's default encoding
    """
    with open(path, 'r') as f_in:
        return f_in.read()
