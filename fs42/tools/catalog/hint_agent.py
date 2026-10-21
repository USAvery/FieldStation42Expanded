#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Filter candidate media against time-dependent metadata hints. Apply folder restrictions and
exclusive matches when choosing content for a scheduling slot.
"""
from fs42.core import paths
from fs42.tools.schedule import schedule_hint


def filter_candidate_entries(when, candidates, meta_hints):
    """
    Filter media using time-dependent metadata rules and prefer exclusive matches

    :param when:       (datetime) proposed broadcast time to evaluate against hints
    :param candidates: (lst<CatalogEntry>) media eligible before metadata filtering
    :param meta_hints: (list) folder-scoped time restrictions and exclusive-selection settings
    :return:           (lst<CatalogEntry>) candidates remaining after metadata and exclusivity checks
    """

    # let's think about what we're doing here:
    # first - separate what has a meta hint and what doesn't
    # second - from items with meta hint, get the list of ones that evaluate to true
    # finally, return the correct set:
    #   - if exclusive is true, return only those items with meta hints that are true
    #   - else, return all items without meta hints + items with meta hints that are true

    has_meta, no_meta = split_meta_hints(candidates, meta_hints)

    filtered_candidates = candidates
    if has_meta:
        valid_candidates = []
        exclusive_candidates = []
        for meta in has_meta:
            candidate_hints = meta['meta']
            candidate = meta['candidate']
            all_passed = True
            found_exclusive = False

            for candidate_hint in candidate_hints:

                if not _entry_passes(candidate_hint, when):
                    all_passed = False
                    break
                if candidate_hint.get('exclusive', False):
                    found_exclusive = True

            if all_passed and not found_exclusive:
                valid_candidates.append(candidate)
            elif found_exclusive:
                exclusive_candidates.append(candidate)

        if len(exclusive_candidates) > 0:
            filtered_candidates = exclusive_candidates
        else:

            filtered_candidates = no_meta + valid_candidates

    return filtered_candidates


def _entry_passes(candidate_hint, when):
    """
    Check whether every recognized time restriction in a metadata hint permits the broadcast time
    """
    for key, klass in schedule_hint.META_HINT_KEYS.items():
        if key in candidate_hint:
            if not klass(candidate_hint[key]).hint(when):
                return False
    return True


def split_meta_hints(candidates, meta_hints):
    """
    Partition media by applicable folder metadata and cache those matches on each entry

    :param candidates: (lst<CatalogEntry>) media whose paths should be matched
    :param meta_hints: (list) folder-scoped metadata rule dictionaries
    :return:           (tuple) candidate-and-rule records followed by entries without matching metadata
    """
    has_meta = []
    no_meta = []
    for candidate in candidates:
        if not candidate.meta_cache:
            meta = _get_meta_hint(candidate, meta_hints)

            if meta:
                candidate.meta_cache = {'has_meta': True, 'meta': meta}
                has_meta.append({'meta': meta, 'candidate': candidate})
            else:
                candidate.meta_cache = {'has_meta': False}
                no_meta.append(candidate)
        else:
            if candidate.meta_cache['has_meta']:
                has_meta.append({'meta': candidate.meta_cache['meta'], 'candidate': candidate})
            else:
                no_meta.append(candidate)

    return has_meta, no_meta


def _get_meta_hint(candidate, meta_hints):
    """
    Collect metadata rules whose tag directories contain the candidate's media path
    """
    meta = None
    for meta_hint in meta_hints:
        for tag in meta_hint['tags']:
            if _is_under(tag, candidate.path):
                if not meta:
                    meta = []
                meta.append(meta_hint)

    return meta


def _is_under(dir_path, file_path):
    """
    Check lexical path containment using whole directory components
    """
    return paths.get_relative_path(file_path, dir_path) is not None


# example:
"""
"hint_meta": [
    { "tags" : "NICKELODEON/bump/face", "day_part" : "morning"},
    { "tags" : "NICKELODEON/bump/face_winter", "day_part" : "morning", "date_range" : "December  1 - December 31"}
]
"""

# print(is_under("one/two/three", "one/two/three/file.ext"))  # True
# print(is_under("one/two/three/", "one/two/three/file.ext"))  # True
# print(is_under("one/two", "one/two/three/file.ext"))  # True
# print(is_under("/one/two", "/one/two/three/file.ext"))  # True
# print(is_under("/one/two", "one/two/three/file.ext"))  # False
# print(is_under("one/two/three/four", "one/two/three/file.ext"))  # False
# print(is_under("one/two/three/", "two/three/file.ext"))  # False
# print(is_under("one/two/three/", "one/three/file.ext"))  # False
#print(HintAgent._is_under("catalog/sitcomx/mim/protected", "catalog/sitcomx/mim/protected/Malcolm in the middle - protected.mkv"))
