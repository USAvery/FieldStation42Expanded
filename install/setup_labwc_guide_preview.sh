#!/usr/bin/env bash

set -euo pipefail

START_MARKER='<!-- FS42 GUIDE PREVIEW START -->'
END_MARKER='<!-- FS42 GUIDE PREVIEW END -->'

if ! command -v labwc >/dev/null 2>&1; then
    echo 'labwc is not installed; guide preview compositor setup is not applicable.'
    exit 0
fi

if ! command -v wtype >/dev/null 2>&1; then
    echo 'Installing wtype for labwc guide preview control...'
    sudo apt-get install -y wtype
fi

config_dir="${XDG_CONFIG_HOME:-$HOME/.config}/labwc"
rc_file="$config_dir/rc.xml"
system_rc='/etc/xdg/labwc/rc.xml'

mkdir -p "$config_dir"

if [ ! -f "$rc_file" ]; then
    if [ ! -f "$system_rc" ]; then
        echo "Could not find $system_rc"
        exit 1
    fi

    cp "$system_rc" "$rc_file"
fi

python3 - "$rc_file" <<'PY'
import sys
from pathlib import Path


path = Path(sys.argv[1])
text = path.read_text()

start_marker = '<!-- FS42 GUIDE PREVIEW START -->'
end_marker = '<!-- FS42 GUIDE PREVIEW END -->'

bindings = '''    <!-- FS42 GUIDE PREVIEW START -->
    <!-- CRT 640x480 -->
    <keybind key="W-F10">
      <action name="ForEach">
        <query identifier="mpv" />
        <then>
          <action name="SetDecorations" decorations="none" />
          <action name="ResizeTo" width="259" height="194" />
          <action name="MoveTo" x="378" y="0" />
        </then>
      </action>
    </keybind>
    <keybind key="W-F11">
      <action name="ForEach">
        <query identifier="mpv" />
        <then>
          <action name="SetDecorations" decorations="none" />
          <action name="ResizeTo" width="265" height="149" />
          <action name="MoveTo" x="375" y="22" />
        </then>
      </action>
    </keybind>
    <keybind key="W-F12">
      <action name="ForEach">
        <query identifier="mpv" />
        <then>
          <action name="SetDecorations" decorations="none" />
          <action name="ResizeTo" width="265" height="113" />
          <action name="MoveTo" x="375" y="40" />
        </then>
      </action>
    </keybind>

    <!-- Normal display 1920x1080 -->
    <keybind key="W-F7">
      <action name="ForEach">
        <query identifier="mpv" />
        <then>
          <action name="SetDecorations" decorations="none" />
          <action name="ResizeTo" width="581" height="436" />
          <action name="MoveTo" x="1232" y="0" />
        </then>
      </action>
    </keybind>
    <keybind key="W-F8">
      <action name="ForEach">
        <query identifier="mpv" />
        <then>
          <action name="SetDecorations" decorations="none" />
          <action name="ResizeTo" width="775" height="436" />
          <action name="MoveTo" x="1135" y="0" />
        </then>
      </action>
    </keybind>
    <keybind key="W-F9">
      <action name="ForEach">
        <query identifier="mpv" />
        <then>
          <action name="SetDecorations" decorations="none" />
          <action name="ResizeTo" width="795" height="338" />
          <action name="MoveTo" x="1125" y="49" />
        </then>
      </action>
    </keybind>
    <!-- FS42 GUIDE PREVIEW END -->'''

if start_marker in text and end_marker in text:
    start = text.index(start_marker)
    end = text.index(end_marker, start) + len(end_marker)

    line_start = text.rfind('\n', 0, start) + 1
    line_end = text.find('\n', end)
    if line_end < 0:
        line_end = len(text)

    text = text[:line_start] + text[line_end + 1:]

if '</keyboard>' in text:
    text = text.replace(
        '  </keyboard>',
        bindings + '\n  </keyboard>',
        1,
    )
elif '</openbox_config>' in text:
    keyboard = (
        '  <keyboard>\n'
        '{}\n'
        '  </keyboard>\n\n'
    ).format(bindings)

    text = text.replace(
        '</openbox_config>',
        keyboard + '</openbox_config>',
        1,
    )
else:
    raise SystemExit('Could not locate labwc keyboard/config closing tag')

path.write_text(text)
PY

labwc_pid="$(pgrep -n labwc || true)"
if [ -n "$labwc_pid" ]; then
    LABWC_PID="$labwc_pid" \
        XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}" \
        WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}" \
        labwc --reconfigure
fi

echo "Configured labwc guide preview controls in $rc_file"
