#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Match paths against relative directory patterns and derive directory names beneath a base path for
catalog filtering.
"""
import os

from fs42.core import paths


def path_ends_with_relative(full_path, relative_path):
    """
    Check whether a file's parent directory ends with the requested path components
    """

    full_dir_parts = paths.split_parts(os.path.dirname(full_path))
    rel_parts = paths.split_parts(relative_path)

    # Get only the directory parts (exclude filename)

    # Check if we have enough parts to match
    if len(rel_parts) > len(full_dir_parts):
        return False

    # Compare the ending directory parts
    return full_dir_parts[-len(rel_parts):] == rel_parts


def path_matches_any_relative(full_path, relative_paths):
    """
    Return the first matching parent-directory suffix, or None
    """

    for relative_path in relative_paths:
        if path_ends_with_relative(full_path, relative_path):
            return relative_path
    return None


def get_dir_from_base(full_path, base_dir):
    """
    Return a file's parent directory relative to a base, or None when outside that base
    """
    return paths.get_relative_path(os.path.dirname(full_path), base_dir)


def path_starts_with(path, pattern):
    """
    Check a lexical directory prefix using complete path components
    """
    if path is None:
        return False

    path_parts = paths.split_parts(path)
    pattern_parts = paths.split_parts(pattern)

    if len(pattern_parts) > len(path_parts):
        return False

    return path_parts[:len(pattern_parts)] == pattern_parts


def match_any_from_base(full_path, base_dir, patterns):
    """
    Return the first directory-prefix pattern matching a file's location beneath a base
    """
    path_from_base = get_dir_from_base(full_path, base_dir)

    for pattern in patterns:
        if path_starts_with(path_from_base, pattern):
            return pattern

    return None
