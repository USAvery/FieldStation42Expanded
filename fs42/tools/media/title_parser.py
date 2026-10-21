#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Extract readable program titles from filenames using custom and built-in patterns, then normalize
separators and capitalization.
"""
import os
import re

from fs42.tools.media._constants import DEFAULT_UPPERCASE_WORDS


def _apply_case(word, upper_words):
    """
    Preserve designated acronyms in uppercase and capitalize other title words
    """
    if word.upper() in upper_words:
        return word.upper()
    return word.capitalize()


def parse_title(in_str, custom_patterns=None, uppercase_words=None):
    """
    Extract a readable program title from a media filename using custom and built-in patterns

    :param in_str:          (str) media path or filename to normalize
    :param custom_patterns: (list) optional regex and capture-group pairs tried before defaults
    :param uppercase_words: (list) additional words to preserve as uppercase acronyms
    :return:                (str) cleaned title with separators removed and word casing normalized
    """
    if not in_str:
        return ''  # Consider defaulting to No Information or No Data to match TV Guides

    filename = in_str.strip()

    # Remove file extension
    filename = os.path.splitext(os.path.basename(filename))[0]

    # Additions to (not replacements of) the default uppercase word set
    upper_words = DEFAULT_UPPERCASE_WORDS
    if uppercase_words:
        upper_words = upper_words | {w.upper() for w in uppercase_words}

    # Define separator pattern - spaces, dots, underscores, dashes
    sep = r'[\s._-]+'

    # Default built-in patterns
    default_patterns = [
        # Title + separators + "Title" + number suffix (e.g., "Show Name - Title1", "Show Name TITLE2")
        (r'^(.+?)' + sep + r'[tT][iI][tT][lL][eE]\d+$', 1),
        # [Group] Title - Episode (release group prefix)
        (r'^\[.+?\]' + sep + r'(.+?)' + sep + r'\d+.*$', 1),
        # Title (including sequels) + year in parentheses - strip the year
        (r'^(.+?)\s*\(\d{4}\)$', 1),
        # Title + separators + season/episode pattern + optional extra (including duplicate episodes like s01e03e03)
        (r'^(.+?)' + sep + r'(?:[sS]\d+(?:' + sep + r'?[eE]\d+)+|[sS]\d+[eE]\d+(?:[eE]\d+)*|\d+[xX]\d+)(?:' + sep +
         r'.*)?$', 1),
        # Title (Year) + separators + season/episode pattern + separators + episode name + separators + extras
        (
            r'^(.+?)(?:\s\(\d{4}\))' + sep + r'(?:[sS]\d+' + sep + r'?[eE]\d+|[sS]\d+[eE]\d+|\d+[xX]\d+)(?:' +
            sep + r'.*)?$',
            1,
        ),
        # Title + version/volume format (show_title_V1-0003) - before simple episode
        (r'^(.+?)[\s._-]+V\d+[\s._-]+\d+$', 1),
        # Title + separators + episode indicators + number (e.g., "e2", "ep3", "episode4", "Episode 1")
        (r'^(.+?)' + sep + r'(?:[eE](?:p(?:isode)?)?(?:' + sep + r')?\d+|[eE]\d+)(?:' + sep + r'.*)?$', 1),
        # Title + separators + simple episode number (but only if followed by episode-like content, not years)
        (r'^(.+?)' + sep + r'\d{1,3}(?:' + sep + r'(?!\d{4}(?:\s|$)).+)+$', 1),
        # Just title (fallback)
        (r'^(.+)$', 1),
    ]

    # Prepend custom patterns so they are tried first (higher priority)
    if custom_patterns:
        patterns = custom_patterns + default_patterns
    else:
        patterns = default_patterns

    for pattern, group in patterns:
        match = re.match(pattern, filename)
        if match:
            title = match.group(group)
            # Clean up the title
            title = re.sub(r'[._-]', ' ', title)  # Replace dots, dashes and underscores with spaces
            title = re.sub(r'\s+', ' ', title)  # Normalize multiple spaces
            title = title.strip()
            # Convert to title case
            return ' '.join(_apply_case(word, upper_words) for word in title.split())

    # Fallback: return cleaned filename
    cleaned = re.sub(r'[._-]', ' ', filename)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return ' '.join(_apply_case(word, upper_words) for word in cleaned.split())
