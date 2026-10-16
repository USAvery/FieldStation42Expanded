import argparse
import datetime
import gzip
import json
import os
import sqlite3
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from fs42.epg_cache import DEFAULT_DB_PATH


DEFAULT_SOURCES = {
    'epgshare_us2': {
        'url': 'https://epgshare01.online/epgshare01/epg_ripper_US2.xml.gz',
    },
}

DEFAULT_USER_AGENT = 'FieldStation42-EPG/1.0'
DEFAULT_PAST_HOURS = 24
DEFAULT_FUTURE_DAYS = 10
BATCH_SIZE = 500


def _local_name(tag):
    return tag.rsplit('}', 1)[-1]


def _first_text(element, tag_name):
    for child in element:
        if _local_name(child.tag) == tag_name:
            text = (child.text or '').strip()
            if text:
                return text
    return ''


def _rating_text(element):
    for child in element:
        if _local_name(child.tag) != 'rating':
            continue
        for value in child:
            if _local_name(value.tag) == 'value':
                text = (value.text or '').strip()
                if text:
                    return text
    return ''


def _parse_xmltv_time(value):
    if not value:
        return None

    parts = value.strip().split()
    digits = parts[0]

    if len(digits) >= 14:
        parsed = datetime.datetime.strptime(digits[:14], '%Y%m%d%H%M%S')
    elif len(digits) >= 12:
        parsed = datetime.datetime.strptime(digits[:12], '%Y%m%d%H%M')
    else:
        return None

    if len(parts) > 1:
        zone = parts[1]
        if len(zone) == 5 and zone[0] in ('+', '-'):
            sign = 1 if zone[0] == '+' else -1
            hours = int(zone[1:3])
            minutes = int(zone[3:5])
            offset = datetime.timedelta(
                hours=hours,
                minutes=minutes,
            )
            parsed = parsed.replace(
                tzinfo=datetime.timezone(sign * offset)
            )

    if parsed.tzinfo is None:
        parsed = parsed.astimezone()

    return int(parsed.timestamp())


def _load_station_mappings(config_dir):
    mappings = {}

    for path in sorted(Path(config_dir).glob('*.json')):
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue

        station = data.get('station_conf')
        if not isinstance(station, dict):
            continue

        epg = station.get('epg')
        if not isinstance(epg, dict):
            continue

        if epg.get('enabled', True) is False:
            continue

        source = epg.get('source')
        channel_id = epg.get('channel_id')

        if not source or not channel_id:
            continue

        mappings.setdefault(source, set()).add(channel_id)

    return mappings


def _load_sources(config_dir):
    sources = {
        name: dict(config)
        for name, config in DEFAULT_SOURCES.items()
    }

    override_path = Path(config_dir) / 'epg_sources.json'
    if not override_path.exists():
        return sources

    try:
        overrides = json.loads(override_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            'Could not read {}: {}'.format(override_path, exc)
        )

    for name, config in overrides.items():
        if not isinstance(config, dict):
            continue
        current = sources.setdefault(name, {})
        current.update(config)

    return sources


def _create_database(path):
    connection = sqlite3.connect(path)

    connection.executescript(
        '''
        PRAGMA journal_mode = OFF;
        PRAGMA synchronous = OFF;
        PRAGMA temp_store = MEMORY;

        CREATE TABLE programmes (
            source TEXT NOT NULL,
            channel_id TEXT NOT NULL,
            start_ts INTEGER NOT NULL,
            end_ts INTEGER NOT NULL,
            title TEXT NOT NULL,
            subtitle TEXT,
            description TEXT,
            category TEXT,
            rating TEXT
        );

        CREATE INDEX programmes_lookup
        ON programmes(source, channel_id, start_ts, end_ts);

        CREATE TABLE source_status (
            source TEXT PRIMARY KEY,
            source_url TEXT NOT NULL,
            updated_ts INTEGER NOT NULL,
            programme_count INTEGER NOT NULL
        );
        '''
    )

    return connection


def _insert_batch(connection, batch):
    if not batch:
        return

    connection.executemany(
        '''
        INSERT INTO programmes (
            source,
            channel_id,
            start_ts,
            end_ts,
            title,
            subtitle,
            description,
            category,
            rating
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        batch,
    )

    batch.clear()


def _import_source(
    connection,
    source_name,
    source_config,
    wanted_channels,
    min_ts,
    max_ts,
):
    url = source_config.get('url')
    if not url:
        raise RuntimeError(
            'EPG source {} does not have a URL'.format(source_name)
        )

    print(
        'Downloading {} for {} mapped channel(s)'.format(
            source_name,
            len(wanted_channels),
        )
    )

    request = urllib.request.Request(
        url,
        headers={
            'User-Agent': source_config.get(
                'user_agent',
                DEFAULT_USER_AGENT,
            ),
            'Accept-Encoding': 'identity',
        },
    )

    batch = []
    imported = 0

    with urllib.request.urlopen(request, timeout=60) as response:
        stream = response

        if url.lower().endswith('.gz'):
            stream = gzip.GzipFile(fileobj=response)

        context = ET.iterparse(stream, events=('start', 'end'))
        _, root = next(context)

        for event, element in context:
            if event != 'end':
                continue

            tag = _local_name(element.tag)

            if tag == 'programme':
                channel_id = element.attrib.get('channel')

                if channel_id in wanted_channels:
                    start_ts = _parse_xmltv_time(
                        element.attrib.get('start')
                    )
                    end_ts = _parse_xmltv_time(
                        element.attrib.get('stop')
                    )

                    if (
                        start_ts is not None
                        and end_ts is not None
                        and end_ts > min_ts
                        and start_ts < max_ts
                    ):
                        title = _first_text(element, 'title')
                        subtitle = _first_text(element, 'sub-title')
                        description = _first_text(element, 'desc')
                        category = _first_text(element, 'category')
                        rating = _rating_text(element)

                        batch.append(
                            (
                                source_name,
                                channel_id,
                                start_ts,
                                end_ts,
                                title or 'Programming',
                                subtitle,
                                description,
                                category,
                                rating,
                            )
                        )
                        imported += 1

                        if len(batch) >= BATCH_SIZE:
                            _insert_batch(connection, batch)

                element.clear()
                root.clear()

            elif tag == 'channel':
                element.clear()
                root.clear()

    _insert_batch(connection, batch)

    connection.execute(
        '''
        INSERT INTO source_status (
            source,
            source_url,
            updated_ts,
            programme_count
        )
        VALUES (?, ?, ?, ?)
        ''',
        (
            source_name,
            url,
            int(datetime.datetime.now().timestamp()),
            imported,
        ),
    )

    print(
        'Imported {} programme(s) from {}'.format(
            imported,
            source_name,
        )
    )

    return imported


def update_epg(
    config_dir='confs',
    db_path=DEFAULT_DB_PATH,
    past_hours=DEFAULT_PAST_HOURS,
    future_days=DEFAULT_FUTURE_DAYS,
):
    mappings = _load_station_mappings(config_dir)

    if not mappings:
        print('No EPG-enabled stations are configured; nothing to update.')
        return 0

    sources = _load_sources(config_dir)

    missing_sources = sorted(
        source for source in mappings
        if source not in sources
    )
    if missing_sources:
        raise RuntimeError(
            'Unknown EPG source(s): {}'.format(
                ', '.join(missing_sources)
            )
        )

    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    temp_path = db_path.with_name(
        '{}.tmp.{}'.format(db_path.name, os.getpid())
    )

    if temp_path.exists():
        temp_path.unlink()

    now_ts = int(datetime.datetime.now().timestamp())
    min_ts = now_ts - (int(past_hours) * 3600)
    max_ts = now_ts + (int(future_days) * 86400)

    connection = None
    total = 0

    try:
        connection = _create_database(temp_path)

        for source_name, wanted_channels in mappings.items():
            total += _import_source(
                connection,
                source_name,
                sources[source_name],
                wanted_channels,
                min_ts,
                max_ts,
            )

        connection.commit()
        connection.execute('ANALYZE')
        connection.commit()
        connection.close()
        connection = None

        if total <= 0:
            raise RuntimeError(
                'EPG update produced no programme data; '
                'keeping the previous cache.'
            )

        os.replace(temp_path, db_path)

        print(
            'EPG cache updated: {} programme(s) -> {}'.format(
                total,
                db_path,
            )
        )

        return total

    except Exception:
        if connection is not None:
            connection.close()

        if temp_path.exists():
            temp_path.unlink()

        raise


def main():
    parser = argparse.ArgumentParser(
        description='Update the FieldStation42 cached XMLTV EPG database.'
    )
    parser.add_argument(
        '--config-dir',
        default='confs',
    )
    parser.add_argument(
        '--db',
        default=str(DEFAULT_DB_PATH),
    )
    parser.add_argument(
        '--past-hours',
        type=int,
        default=DEFAULT_PAST_HOURS,
    )
    parser.add_argument(
        '--future-days',
        type=int,
        default=DEFAULT_FUTURE_DAYS,
    )

    args = parser.parse_args()

    try:
        update_epg(
            config_dir=args.config_dir,
            db_path=args.db,
            past_hours=args.past_hours,
            future_days=args.future_days,
        )
    except Exception as exc:
        print(
            'EPG update failed: {}'.format(exc),
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
