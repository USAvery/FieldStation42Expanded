#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Define On Demand menu choices and bounded catalog queries
"""
PAGE_SIZE = 10
# Pi 4 cannot decode YouTube's preferred 4K AV1/VP9 streams in hardware.
# Select AVC + AAC at a resolution and frame rate suitable for direct playback.
YOUTUBE_FORMAT = ('bestvideo[vcodec^=avc1][height<=1080][fps<=30]+'
                  'bestaudio[acodec^=mp4a]/best[vcodec^=avc1][height<=1080][fps<=30]')
CATEGORIES = [
    {'id': 'top', 'title': 'Top Picks'},
    {'id': 'search', 'title': 'Search'},
    {'id': 'movies', 'title': 'Movies'},
    {'id': 'tv', 'title': 'TV Shows'},
    {'id': 'kids', 'title': 'Kids'},
    {'id': 'recent', 'title': 'Recently Added'},
    {'id': 'short', 'title': 'Short Features'},
    {'id': 'long', 'title': 'Long Features'},
    {'id': 'channels', 'title': 'By Channel'},
    {'id': 'all', 'title': 'All Titles'},
    {'id': 'youtube', 'title': 'YouTube'},
]
CATEGORY_FILTERS = {
    'movies': "kind = 'movie'",
    'tv': "kind = 'episode'",
    'kids': 'kids = 1',
    'short': 'duration < 1800',
    'long': 'duration >= 5400',
}
CATALOG_QUERY = '''
    WITH library AS (
        SELECT c.id, c.station, c.path, c.title, c.duration, c.tag, c.count AS play_count,
               {metadata} AS meta,
               media_kind({metadata}, c.path) AS kind,
               kids_content({metadata}, c.tag) AS kids,
               ROW_NUMBER() OVER (
                   PARTITION BY COALESCE(NULLIF(c.realpath, ''), c.path)
                   ORDER BY c.id
               ) AS duplicate
        FROM catalog_entries AS c {join}
        WHERE c.station IN ({stations}) AND c.content_type = 'feature'
              AND c.media_type = 'video' AND c.duration > 0
              AND c.path NOT LIKE 'http://%' AND c.path NOT LIKE 'https://%'
    )
    SELECT {columns} FROM library WHERE duplicate = 1 {filters}
'''
