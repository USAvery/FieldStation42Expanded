#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Select and draw station or program logos, including animated and time-dependent variants. Use player
status to suppress logos during breaks and restart their display timing when programs resume.
"""
import os
import glob
import json
import random
import datetime

from PySide6.QtGui import QImage
from PySide6.QtCore import QRectF
from PySide6.QtGui import QPixmap

from fs42.core import paths
from fs42.core import logger as project_logger
from fs42.core.station_manager import StationManager

from fs42.tools.osd.osd_layout import HAlignment
from fs42.tools.osd.osd_layout import VAlignment
from fs42.tools.osd._constants import ContentType
from fs42.tools.osd.osd_layout import calc_margin_px
from fs42.tools.osd.osd_layout import frac_to_size_px
from fs42.tools.osd.display.display import BaseDisplay
from fs42.tools.osd.osd_layout import calc_draw_position


_logger = project_logger.setup('fs42.tools.osd.display.logo_display')


class LogoDisplay(BaseDisplay):
    """
    Select and render station or program logos while feature content is playing
    """

    def __init__(self, config):
        """
        Initialize logo selection and animation state, then read the current channel

        :param config: (LogoDisplayConfig) fallback image, layout, and visibility settings
        """
        super(LogoDisplay, self).__init__(config)
        self.station_manager = StationManager()

        self.current_logo_frames = []
        self.current_logo_size = (0, 0)
        self.current_frame_durations = []
        self.current_frame_index = 0
        self.frame_timer = 0.0
        self.is_animated = False

        self.current_channel_info = {}
        self.channel_config = {}
        self.time_since_change = float('inf')
        self.current_content_type = ContentType.UNKNOWN
        self.available_logos = []
        self.current_logo_path = None
        self.is_displaying_osd_default_logo = False

        self.main_config = None

        self.check_status()

    # -------------------------------------------------------------------------
    # Helpers to load logos and config
    # -------------------------------------------------------------------------

    def get_available_logos(self, dir_path):
        """
        List supported image files directly inside a logo directory

        :param dir_path: (str) directory to scan without descending into subdirectories
        :return:         (lst<str>) PNG, JPEG, GIF, and BMP paths with lower- or uppercase extensions
        """
        extensions = ['*.png', '*.jpg', '*.jpeg', '*.gif', '*.bmp']
        found = []
        for ext in extensions:
            found.extend(glob.glob(os.path.join(dir_path, ext)))
            found.extend(glob.glob(os.path.join(dir_path, ext.upper())))
        return found

    def load_main_config(self):
        """
        Read and cache global settings, using an empty dictionary if loading fails
        """
        if self.main_config is not None:
            return self.main_config

        cfg_path = os.path.join(paths.PROJECT_ROOT, 'confs', 'main_config.json')

        try:
            with open(cfg_path, 'r') as f:
                self.main_config = json.load(f)
        except Exception:
            self.main_config = {}

        return self.main_config

    # -------------------------------------------------------------------------
    # Tag-based content directory: logo_dir/<first_tag>/
    #    - tags derived from the station's schedule (day/hour-based)
    # -------------------------------------------------------------------------

    def find_content_logo_dir(self, base_dir, station_data):
        """
        Find a program-specific logo directory from the playing file or current schedule tag

        Prefer the first directory beneath content_dir in the playing file's path. If
        that fails, use the current schedule slot's first tag. Try both sanitized and
        original tag names when locating a directory.

        :param base_dir:     (str) root directory containing program logo folders
        :param station_data: (dict) station content directory and weekday schedule settings
        :return:             (str) matching logo directory, or None when none exists
        """

        def normalize_tag(tag):
            """
            Return a trimmed tag and a version with spaces and path separators replaced by underscores
            """
            stripped = tag.strip()
            safe = (stripped.replace(' ', '_').replace('/', '_').replace('\\', '_').replace(':', '_'))
            return stripped, safe

        def logo_dir_for_tag(tag):
            """
            Find an existing logo subdirectory for the sanitized or original tag name
            """
            stripped, safe = normalize_tag(tag)

            if not stripped:
                return None

            candidate = os.path.join(base_dir, safe)
            if os.path.exists(candidate) and os.path.isdir(candidate):
                return candidate

            if stripped != safe:
                candidate_orig = os.path.join(base_dir, stripped)
                if os.path.exists(candidate_orig) and os.path.isdir(candidate_orig):
                    return candidate_orig

            return None

        # ---------------------------------------------------------------------
        # 1) Prefer the currently playing file path.
        # ---------------------------------------------------------------------

        file_path = self.current_channel_info.get('file_path')
        content_dir = station_data.get('content_dir')

        if file_path and content_dir:
            file_parts = paths.split_parts(file_path)
            content_parts = paths.split_parts(content_dir)

            # Find content_dir inside file_path, whether file_path is relative
            # or absolute. Example:
            #   file_path:    /home/user/FieldStation42/catalog/MTV/daria/foo.mp4
            #   content_dir:  catalog/MTV
            #   resolved tag: daria
            for i in range(0, len(file_parts) - len(content_parts) + 1):
                if file_parts[i:i + len(content_parts)] == content_parts:
                    tag_index = i + len(content_parts)
                    if tag_index < len(file_parts) - 1:
                        tag = file_parts[tag_index]
                        match = logo_dir_for_tag(tag)
                        if match:
                            return match
                    break

        elif file_path:
            # Last-resort file-path fallback if content_dir is unavailable.
            # For catalog/STATION/tag/file.mp4, parent.name is usually tag.
            parent_tag = os.path.basename(os.path.dirname(file_path))
            match = logo_dir_for_tag(parent_tag)
            if match:
                return match

        # ---------------------------------------------------------------------
        # 2) Fall back to schedule slot tag behavior.
        # ---------------------------------------------------------------------

        now = datetime.datetime.now()
        day_key = now.strftime('%A').lower()  # "monday", "tuesday", etc.
        day_schedule = station_data.get(day_key)

        if not isinstance(day_schedule, dict):
            return None

        # Try exact hour match first
        hour_str = str(now.hour)
        slot = day_schedule.get(hour_str)

        # Optional fallback: latest hour <= now.hour
        if slot is None:
            try:
                sorted_hours = sorted((int(h) for h in day_schedule.keys() if h.isdigit()))
                eligible = [h for h in sorted_hours if h <= now.hour]
                if eligible:
                    best_hour = str(eligible[-1])
                    slot = day_schedule.get(best_hour)
            except Exception:
                slot = None

        if not isinstance(slot, dict):
            return None

        val = slot.get('tags') or slot.get('tag')
        if not val:
            return None

        # Support either a single string or a list/tuple of tags
        if isinstance(val, str):
            first_tag = val
        elif isinstance(val, (list, tuple)) and val:
            first_tag = str(val[0])
        else:
            return None

        return logo_dir_for_tag(first_tag)

    # -------------------------------------------------------------------------
    # Month-based temporal directory: logo_dir/<Month>/ or ranges
    # -------------------------------------------------------------------------

    def find_temporal_logo_dir(self, base_dir):
        """
        Find a logo subdirectory named for the current month or an applicable day range

        :param base_dir: (str) root directory containing seasonal logo folders
        :return:         (str) first matching directory, or None when no seasonal folder matches
        """
        today = datetime.date.today()
        month_name = today.strftime('%B')
        day = today.day

        if not os.path.exists(base_dir):
            return None

        for name in os.listdir(base_dir):
            sub = os.path.join(base_dir, name)
            if not os.path.isdir(sub):
                continue

            name = os.path.basename(sub)

            # Exact month match, e.g. "October"
            if name == month_name:
                return sub

            # Month range: "October 1 - October 31"
            parts = name.split(' - ')
            if len(parts) == 2:
                left, right = parts
                lp = left.split()
                rp = right.split()
                if len(lp) == 2 and len(rp) == 2:
                    m1, d1s = lp
                    m2, d2s = rp
                    if m1 == m2 == month_name:
                        try:
                            d1 = int(d1s)
                            d2 = int(d2s)
                            if d1 <= day <= d2:
                                return sub
                        except ValueError:
                            pass

        return None

    # -------------------------------------------------------------------------
    # Day-part detection from main_config.json (start_hour / end_hour)
    # -------------------------------------------------------------------------

    def get_current_day_part(self):
        """
        Determine the current day_part from main_config.json
        """
        cfg = self.load_main_config()
        day_parts = cfg.get('day_parts')
        if not day_parts or not isinstance(day_parts, dict):
            return None

        now = datetime.datetime.now()
        now_hour = now.hour

        for name, spec in day_parts.items():
            if not isinstance(spec, dict):
                continue
            start = spec.get('start_hour')
            end = spec.get('end_hour')
            if start is None or end is None:
                continue

            # Same-day range (e.g., 6 → 10)
            if start <= end:
                if start <= now_hour < end:
                    return name
            else:
                # Wrap past midnight (e.g., 21 → 2)
                if now_hour >= start or now_hour < end:
                    return name

        return None

    # -------------------------------------------------------------------------
    # Weekday helper: "Monday", "Tuesday", etc.
    # -------------------------------------------------------------------------

    def get_current_weekday(self):
        """
        Return current weekday name, e.g. "Friday"
        """
        today = datetime.date.today()
        return today.strftime('%A')

    # -------------------------------------------------------------------------
    # Logo selection logic with full hierarchy
    # -------------------------------------------------------------------------

    def select_logo_for_channel(self, station_data):
        """
        Choose a station logo using program and seasonal folders before the base directory

        :param station_data: (dict) station logo directory, preferred image, and selection settings
        :return:             (str) selected image path, or None when no candidate is available
        """
        multi = station_data.get('multi_logo', 'single').lower()
        if multi == 'off':
            multi = 'single'
        elif multi == 'random':
            multi = 'multi'
        if multi not in ('single', 'multi'):
            multi = 'single'

        content_dir = station_data.get('content_dir')
        logo_dir = station_data.get('logo_dir')
        default_logo_name = station_data.get('default_logo')

        # Original FS42 semantics: logo_dir relative to content_dir
        # (catalog/<STATION>/<logo_dir>), all rooted at paths.PROJECT_ROOT.
        if content_dir and logo_dir:
            base_dir = os.path.join(paths.PROJECT_ROOT, content_dir, logo_dir)
        elif logo_dir:
            p = os.fspath(logo_dir)
            base_dir = p if os.path.isabs(p) else os.path.join(paths.PROJECT_ROOT, logo_dir)
        else:
            return None

        override_dirs = []

        # 1) Content tag override (derived from the station's schedule)
        cdir = self.find_content_logo_dir(base_dir, station_data)
        if cdir:
            override_dirs.append(cdir)

        # Temporal hints: month, weekday, day_part
        month_dir = self.find_temporal_logo_dir(base_dir)
        day_part_name = self.get_current_day_part()
        weekday_name = self.get_current_weekday()

        # Normalize day_part to filesystem-friendly name
        day_part_folder = None
        if day_part_name:
            day_part_folder = day_part_name.replace(' ', '_')

        # Helper to add a candidate directory if it exists and isn't already listed
        def add_candidate(path):
            """
            Add an existing override directory once, preserving selection priority
            """
            if path and os.path.exists(path) and os.path.isdir(path):
                if path not in override_dirs:
                    override_dirs.append(path)

        # 2) Month-based combinations first (most specific → less specific)
        if month_dir:
            # Month / Weekday / day_part
            if weekday_name and day_part_folder:
                add_candidate(os.path.join(month_dir, weekday_name, day_part_folder))

            # Month / Weekday
            if weekday_name:
                add_candidate(os.path.join(month_dir, weekday_name))

            # Month / day_part
            if day_part_folder:
                add_candidate(os.path.join(month_dir, day_part_folder))

            # Month-only
            add_candidate(month_dir)
        else:
            # 3) Only use generic weekday/day_part when month_dir is not present
            # Weekday / day_part
            if weekday_name and day_part_folder:
                add_candidate(os.path.join(base_dir, weekday_name, day_part_folder))

            # Weekday-only
            if weekday_name:
                add_candidate(os.path.join(base_dir, weekday_name))

            # day_part-only
            if day_part_folder:
                add_candidate(os.path.join(base_dir, day_part_folder))

        def pick_single():
            """
            Prefer the named default logo in an override folder, then fall back to another available image
            """
            # Try override dirs in order
            for d in override_dirs:
                logos = self.get_available_logos(d)
                if logos:
                    if default_logo_name:
                        cand = os.path.join(d, default_logo_name)
                        if os.path.exists(cand):
                            return cand
                    return random.choice(logos)

            # Fallback: default_logo in base_dir if defined
            if default_logo_name:
                cand = os.path.join(base_dir, default_logo_name)
                if os.path.exists(cand):
                    return cand

            # Fallback: any logo in base_dir
            logos = self.get_available_logos(base_dir)
            if logos:
                return random.choice(logos)

            return None

        def pick_multi():
            """
            Choose a random image from override folders, falling back to the base logo directory
            """
            pool = []
            for d in override_dirs:
                pool.extend(self.get_available_logos(d))
            if pool:
                self.available_logos = pool
                return random.choice(pool)

            logos = self.get_available_logos(base_dir)
            if logos:
                self.available_logos = logos
                return random.choice(logos)

            return None

        return pick_single() if multi == 'single' else pick_multi()

    # -------------------------------------------------------------------------
    # Status reading and content tracking
    # -------------------------------------------------------------------------

    def check_status(self):
        """
        Track channel, program, and content-type changes to reload logos and reset timing

        Reload on channel or title changes. When feature content resumes after a break,
        restart its display interval and reshuffle stations configured for multiple logos.
        """
        status = self._get_status()
        if status is None:
            return

        prev_net = self.current_channel_info.get('network_name')
        prev_title = self.current_channel_info.get('title')
        prev_type = self.current_content_type

        new_net = status.get('network_name')
        new_title = status.get('title')

        # Always update current_channel_info to what we just read
        self.current_channel_info = status

        # Always classify the current content so our draw() logic is up to date
        new_type = status.get('content_type') or ContentType.UNKNOWN
        self.current_content_type = new_type

        multi_setting = self.channel_config.get('multi_logo', 'single').lower()
        if multi_setting == 'random':
            multi_setting = 'multi'

        # 1) Network change: new station or channel
        if new_net != prev_net:
            self.time_since_change = 0.0
            self.available_logos = []
            self.load_logo_for_channel(status)
            return

        # 2) Same network, but title changed (likely program change or interstitial)
        if new_title != prev_title:
            # If we just entered FEATURE content, reset the timer
            if prev_type != ContentType.FEATURE and new_type == ContentType.FEATURE:
                self.time_since_change = 0.0

            # Reload logo on any title change — show-specific (tag-based) logos
            # may differ between shows, and multi-logo stations should reshuffle
            self.load_logo_for_channel(status)

            return

        # 3) Same network and same title, but content type may have changed
        #    (e.g., we returned from a bump/commercial to FEATURE, but title
        #    stayed the same).
        if prev_type != ContentType.FEATURE and new_type == ContentType.FEATURE:
            self.time_since_change = 0.0
            if multi_setting in ('multi', ):
                self.load_logo_for_channel(status)

    # -------------------------------------------------------------------------
    # Logo loading
    # -------------------------------------------------------------------------

    def load_animated_gif(self, path):
        """
        Decode GIF frames into Qt pixmaps and record their display durations

        :param path: (str) animated image filename
        :return:     (bool) whether loading succeeded; failures clear the current frames
        """
        try:
            from PIL import Image

            self.clear_logo_frames()
            with Image.open(path) as img:
                frames = []
                durations = []
                width, height = img.size

                for i in range(img.n_frames):
                    img.seek(i)
                    frame = img.convert('RGBA')
                    duration = max(img.info.get('duration', 100) / 1000.0, 0.01)
                    fw, fh = frame.size

                    qimg = QImage(frame.tobytes(), fw, fh, QImage.Format.Format_RGBA8888).copy()
                    frames.append(QPixmap.fromImage(qimg))
                    durations.append(duration)

                self.current_logo_frames = frames
                self.current_frame_durations = durations
                self.current_logo_size = (width, height)
                self.current_frame_index = 0
                self.frame_timer = 0.0
                self.is_animated = len(frames) > 1

                _logger.info('[INFO] Loaded animated logo: {}'.format(path))
                return True

        except Exception as e:
            _logger.error('[ERROR] Error loading animated logo {0}: {1}'.format(path, e))
            self.clear_logo_frames()
            return False

    def clear_logo_frames(self):
        """
        Discard loaded logo images and reset animation and path state
        """
        self.current_logo_frames = []
        self.current_logo_path = None
        self.current_frame_durations = []
        self.current_frame_index = 0
        self.frame_timer = 0.0
        self.is_animated = False

    def load_static_logo(self, path):
        """
        Replace the current frames with a single image, clearing them if decoding fails

        :param path: (str) image filename to load into a Qt pixmap
        """
        self.clear_logo_frames()
        try:
            pixmap = QPixmap(path)
            if pixmap.isNull():
                raise ValueError('Could not decode image: {}'.format(path))
            self.current_logo_frames = [pixmap]
            self.current_frame_durations = [0.0]
            self.current_logo_size = (pixmap.width(), pixmap.height())
            self.current_frame_index = 0
            self.frame_timer = 0.0
            self.is_animated = False
            _logger.info('[INFO] Loaded static logo: {}'.format(path))
        except Exception as e:
            _logger.error('[ERROR] Error loading static logo {0}: {1}'.format(path, e))
            self.clear_logo_frames()

    def load_logo_for_channel(self, info):
        """
        Load the selected station logo or configured fallback, respecting logo suppression

        :param info: (dict) player status containing the network_name used to locate station settings
        """
        logo_path = None
        self.channel_config = {}
        self.is_displaying_osd_default_logo = False

        net = info.get('network_name')
        show_logo = True

        if net:
            try:
                station = self.station_manager.station_by_name(net)
                if isinstance(station, dict):
                    self.channel_config = station

                    if station.get('show_logo', True) is False:
                        show_logo = False
                        self.clear_logo_frames()
                        return

                    selected = self.select_logo_for_channel(station)
                    if selected is not None:
                        logo_path = selected
                else:
                    _logger.warning('[WARNING] No station data for {}'.format(net))
            except Exception as e:
                _logger.error('[ERROR] Failed to get station data for {0}: {1}'.format(net, e))

        if not logo_path and show_logo:
            if self.config.default_show_logo and self.config.default_logo:
                candidate = os.fspath(self.config.default_logo)
                if os.path.exists(candidate):
                    logo_path = candidate
                    self.is_displaying_osd_default_logo = True
                else:
                    _logger.warning('[WARNING] OSD default logo not found: {}'.format(self.config.default_logo))

        if logo_path and os.path.exists(logo_path):
            if (self.current_logo_path == str(logo_path)
                    and not (self.channel_config.get('multi_logo', 'single').lower() in ('multi', 'random')
                             and not self.is_displaying_osd_default_logo)):
                return

            if str(logo_path).lower().endswith('.gif'):
                if not self.load_animated_gif(str(logo_path)):
                    self.load_static_logo(str(logo_path))
            else:
                self.load_static_logo(str(logo_path))
            if self.current_logo_frames:
                self.current_logo_path = str(logo_path)
        else:
            self.clear_logo_frames()
            self.is_displaying_osd_default_logo = False

    # -------------------------------------------------------------------------
    # Update & Draw
    # -------------------------------------------------------------------------

    def update(self, dt):
        """
        Poll channel state and advance the current logo animation by at most one frame

        :param dt: (float) elapsed time since the previous update in seconds
        """
        super(LogoDisplay, self).update(dt)

        if self.is_animated and self.current_logo_frames:
            self.frame_timer += dt
            dur = self.current_frame_durations[self.current_frame_index]
            if dur <= 0.0:
                dur = 0.1
            if self.frame_timer >= dur:
                self.frame_timer -= dur
                self.current_frame_index = (self.current_frame_index + 1) % len(self.current_logo_frames)

    def is_visible(self):
        """
        Show loaded logos during features while station or fallback timing allows them
        """
        if (not self.current_logo_frames or self.current_frame_index >= len(self.current_logo_frames)):
            return False

        if self.current_content_type != ContentType.FEATURE:
            return False

        if self.is_displaying_osd_default_logo:
            permanent = self.config.default_logo_permanent
        else:
            permanent = self.channel_config.get('logo_permanent', False)

        display_time = (float(self.channel_config.get('logo_display_time'))
                        if not self.is_displaying_osd_default_logo
                        and self.channel_config.get('logo_display_time') is not None else self.config.display_time)

        if (not permanent and not self.config.always_show and self.time_since_change >= display_time):
            return False

        return True

    def draw(self, painter, screen_w, screen_h):
        """
        Paint the current logo frame when feature content and visibility settings allow it

        Apply station layout and opacity overrides, or fallback-logo settings when using
        the global default. Stretch the frame to the configured width and height.

        :param painter:  (QPainter) active painter for the OSD window
        :param screen_w: (int) drawing surface width in pixels
        :param screen_h: (int) drawing surface height in pixels
        """
        if not self.is_visible():
            return

        width = float(self.channel_config.get('logo_width', self.config.width))
        height = float(self.channel_config.get('logo_height', self.config.height))

        x_margin = float(self.channel_config.get('logo_x_margin', self.config.x_margin))
        y_margin = float(self.channel_config.get('logo_y_margin', self.config.y_margin))

        halign_str = self.channel_config.get('logo_halign', self.config.halign.value)
        valign_str = self.channel_config.get('logo_valign', self.config.valign.value)

        try:
            halign = HAlignment[halign_str.upper()]
        except Exception:
            halign = self.config.halign

        try:
            valign = VAlignment[valign_str.upper()]
        except Exception:
            valign = self.config.valign

        w = frac_to_size_px(width, screen_w)
        h = frac_to_size_px(height, screen_h)
        x_margin_px = calc_margin_px(x_margin, screen_w)
        y_margin_px = calc_margin_px(y_margin, screen_h)
        x, y = calc_draw_position(screen_w, screen_h, w, h, halign, valign, x_margin_px, y_margin_px)

        pixmap = self.current_logo_frames[self.current_frame_index]

        alpha = (self.config.default_logo_alpha if self.is_displaying_osd_default_logo else float(
            self.channel_config.get('logo_alpha', self.config.default_logo_alpha)))

        painter.setOpacity(alpha)
        painter.drawPixmap(QRectF(x, y, w, h), pixmap, QRectF(pixmap.rect()))
        painter.setOpacity(1.0)
