/*
This Source Code Form is subject to the Mozilla Public License, v. 2.0.
See https://mozilla.org/MPL/2.0/.
*/
window.app = window.app || {};
app.tools = app.tools || {};
app.tools.guide = (function () {
    let self = {};
    /**
     * Set up the guide page
     */
    self.setup = function () {
        // Initialize page layout
        document.addEventListener('DOMContentLoaded', async function () {
            window.fs42Common.initTheme();
            const content = [
                '',
                '        <div class="pure-u-1">',
                '            <iframe id="guide-frame" src="/static/guide_frame.html" title="Guide">',
                '                <p>Your browser does not support iframes. Please <a href="/static/guide_frame.html">click here to view the Guide</a>.</p>',
                '            </iframe>',
                '        </div>',
                '    '
            ].join('\n');
            document.body.innerHTML = await window.fs42Common.createPageLayout('Guide', content);
            setupDebugToggleButton();
        });

        // Add a "Show File Names" toggle switch on the same row as the page title.
        // The guide itself lives in the same-origin iframe, so we call its
        // exposed toggle function and reflect state via shared localStorage.
        /**
         * Setup Debug Toggle Button
         */
        function setupDebugToggleButton() {
            const heading = document.querySelector('.pure-g h1');
            if (!heading) {
                return;
            }
            injectDebugToggleStyles();

            // Put the title and switch on one flex row
            heading.style.display = 'flex';
            heading.style.alignItems = 'center';
            heading.style.justifyContent = 'space-between';
            heading.style.gap = '1em';
            const isOn = function () {
                return localStorage.getItem('fs42-guide-debug') === 'true';
            };
            const control = document.createElement('label');
            control.className = 'debug-toggle';
            control.title = 'Show raw file names instead of normalized titles (shortcut: d)';
            control.innerHTML = [
                '',
                '        <span class="debug-toggle-label">Show File Names</span>',
                '        <span class="debug-toggle-track" aria-hidden="true">',
                '            <span class="debug-toggle-thumb"></span>',
                '        </span>',
                '        <input type="checkbox" class="debug-toggle-input" role="switch">',
                '    '
            ].join('\n');
            heading.appendChild(control);
            const input = control.querySelector('.debug-toggle-input');
            /**
             * Render
             */
            function render() {
                const on = isOn();
                input.checked = on;
                control.classList.toggle('is-on', on);
            }
            input.addEventListener('change', function () {
                const frame = document.getElementById('guide-frame');
                const win = frame && frame.contentWindow;
                if (win && typeof win.setDebugFilename === 'function') {
                    win.setDebugFilename(input.checked);
                }
                else {
                    // Iframe not ready yet — flip the shared setting directly.
                    localStorage.setItem('fs42-guide-debug', String(input.checked));
                }
                render();
            });
            render();
        }
        /**
         * Inject Debug Toggle Styles
         */
        function injectDebugToggleStyles() {
            if (document.getElementById('debug-toggle-styles')) {
                return;
            }
            const style = document.createElement('style');
            style.id = 'debug-toggle-styles';
            style.textContent = [
                '',
                '        .debug-toggle {',
                '            display: inline-flex;',
                '            align-items: center;',
                '            gap: 0.55em;',
                '            font-size: 0.42em;',
                '            font-weight: 500;',
                '            letter-spacing: 0.04em;',
                '            text-transform: uppercase;',
                '            color: #8b95a5;',
                '            cursor: pointer;',
                '            user-select: none;',
                '            white-space: nowrap;',
                '            transition: color 0.2s ease;',
                '        }',
                '        .debug-toggle:hover { color: #c5ccd6; }',
                '        .debug-toggle.is-on { color: #61afef; }',
                '        .debug-toggle .debug-toggle-input {',
                '            position: absolute;',
                '            opacity: 0;',
                '            width: 0;',
                '            height: 0;',
                '        }',
                '        .debug-toggle-track {',
                '            position: relative;',
                '            width: 2.6em;',
                '            height: 1.35em;',
                '            border-radius: 1em;',
                '            background: #2b313b;',
                '            border: 1px solid #3a4150;',
                '            transition: background 0.2s ease, border-color 0.2s ease;',
                '            flex: none;',
                '        }',
                '        .debug-toggle-thumb {',
                '            position: absolute;',
                '            top: 50%;',
                '            left: 0.16em;',
                '            width: 1em;',
                '            height: 1em;',
                '            border-radius: 50%;',
                '            background: #c5ccd6;',
                '            transform: translateY(-50%);',
                '            transition: transform 0.2s ease, background 0.2s ease;',
                '            box-shadow: 0 1px 2px rgba(0, 0, 0, 0.4);',
                '        }',
                '        .debug-toggle.is-on .debug-toggle-track {',
                '            background: rgba(97, 175, 239, 0.25);',
                '            border-color: #61afef;',
                '        }',
                '        .debug-toggle.is-on .debug-toggle-thumb {',
                '            transform: translate(1.25em, -50%);',
                '            background: #61afef;',
                '        }',
                '        .debug-toggle:focus-within .debug-toggle-track {',
                '            outline: 2px solid #61afef;',
                '            outline-offset: 2px;',
                '        }',
                '    '
            ].join('\n');
            document.head.appendChild(style);
        }
        self.setupDebugToggleButton = setupDebugToggleButton;
        self.injectDebugToggleStyles = injectDebugToggleStyles;
    };
    return self;
})();
