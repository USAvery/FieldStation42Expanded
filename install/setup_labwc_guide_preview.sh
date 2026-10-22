#!/usr/bin/env bash
set -euo pipefail

if ! command -v labwc >/dev/null 2>&1; then
    echo 'labwc is not installed; compositor setup is not applicable.'
    exit 0
fi
if ! command -v wtype >/dev/null 2>&1; then
    sudo apt-get install -y wtype
fi

config_dir="${XDG_CONFIG_HOME:-$HOME/.config}/labwc"
rc_file="$config_dir/rc.xml"
mkdir -p "$config_dir"
if [ ! -f "$rc_file" ]; then
    cp /etc/xdg/labwc/rc.xml "$rc_file"
fi

python3 - "$rc_file" <<'PY'
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text()

def remove_section(source, label):
    pattern = r'(?m)^[ \t]*<!-- FS42 ' + label + r' START -->.*?<!-- FS42 ' + label + r' END -->[ \t]*\n?'
    return re.sub(pattern, '', source, flags=re.S)

def bind(key, actions):
    return ('    <keybind key="{}"><action name="ForEach"><query identifier="mpv" />'
            '<then>{}</then></action></keybind>').format(key, actions)

for label in ['GUIDE PREVIEW', 'PLAYBACK BACKDROP']:
    text = remove_section(text, label)

bindings = [bind('W-F20', '<action name="SetDecorations" decorations="none" />'
                        '<action name="MoveTo" x="0" y="0" />')]
for axis, modifier in [('x', 'C'), ('y', 'S')]:
    for bit in range(12):
        action = '<action name="MoveRelative" {}="{}" />'.format(axis, 1 << bit)
        bindings.append(bind('W-{}-F{}'.format(modifier, bit + 1), action))
keyboard = ('    <!-- FS42 GUIDE PREVIEW START -->\n' +
            '\n'.join(bindings) + '\n    <!-- FS42 GUIDE PREVIEW END -->')
if '</keyboard>' in text:
    text = re.sub(r'(?m)^[ \t]*</keyboard>', lambda match: keyboard + '\n  </keyboard>',
                  text, count=1)
else:
    text = text.replace('</openbox_config>',
                        '  <keyboard>\n' + keyboard + '\n  </keyboard>\n</openbox_config>', 1)

rules = '''    <!-- FS42 PLAYBACK BACKDROP START -->
    <windowRule title="FieldStation42 Playback Backdrop" serverDecoration="no"
                skipTaskbar="yes" skipWindowSwitcher="yes" ignoreFocusRequest="yes">
      <action name="Lower" />
      <action name="ForEach"><query identifier="mpv" />
        <then><action name="Focus" /></then>
      </action>
    </windowRule>
    <windowRule title="FieldStation42 Channel Transition" serverDecoration="no"
                skipTaskbar="yes" skipWindowSwitcher="yes">
      <action name="ToggleAlwaysOnTop" />
    </windowRule>
    <windowRule title="FieldStation42 Guide Overlay" serverDecoration="no"
                skipTaskbar="yes" skipWindowSwitcher="yes">
      <action name="ToggleAlwaysOnTop" />
    </windowRule>
    <!-- FS42 PLAYBACK BACKDROP END -->'''
if '</windowRules>' in text:
    text = re.sub(r'(?m)^[ \t]*</windowRules>', lambda match: rules + '\n  </windowRules>',
                  text, count=1)
else:
    text = text.replace('</openbox_config>',
                        '  <windowRules>\n' + rules + '\n  </windowRules>\n</openbox_config>', 1)
ET.fromstring(text)
if text != path.read_text():
    path.write_text(text)
PY

labwc_pid="$(pgrep -n labwc || true)"
if [ -n "$labwc_pid" ]; then
    LABWC_PID="$labwc_pid" \
        XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}" \
        WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}" labwc --reconfigure
fi
echo "Configured exact guide geometry and playback surfaces in $rc_file"
