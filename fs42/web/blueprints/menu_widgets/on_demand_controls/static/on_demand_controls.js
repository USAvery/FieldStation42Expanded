/* This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0. */
window.app = window.app || {};
app.menu_widgets = app.menu_widgets || {};
app.menu_widgets.on_demand_controls = (function() {
    let self = {};

    class PlaybackControls {
        constructor() {
            this.root = document.getElementById('on-demand-controls');
            this.timeline = document.getElementById('od-transport-timeline');
            this.toggle = document.getElementById('od-transport-toggle');
            this.status = document.getElementById('od-transport-status');
            this.buttons = ['od-transport-rewind', 'od-transport-toggle', 'od-transport-forward']
                .map(id => document.getElementById(id));
            this.state = {};
            this.draft = null;
            this.pending_until = 0;
            this.last_interaction = 0;
            this.onState = this.onState.bind(this);
            this.onKeydown = this.onKeydown.bind(this);
        }

        onState(event) {
            const state = event.detail;
            const was_visible = !this.root.hidden;
            if (state.session_id !== this.state.session_id || !state.visible) {
                this.draft = null;
                this.pending_until = 0;
                this.status.textContent = '';
            }
            this.state = state;
            document.body.classList.toggle('on-demand-playing', !!state.active && !state.menu_visible);
            this.root.hidden = !state.active || !state.visible;
            if (this.root.hidden) return;
            if (this.pending_until && (Math.abs(state.position - this.draft) < 2 || Date.now() > this.pending_until)) {
                this.draft = null;
                this.pending_until = 0;
            }
            document.getElementById('od-transport-title').textContent = state.title || '';
            document.getElementById('od-transport-source').textContent = state.source || 'On Demand';
            document.getElementById('od-transport-duration').textContent = formatDuration(state.duration);
            this.toggle.querySelector('.od-icon-play').style.display = state.paused ? 'block' : 'none';
            this.toggle.querySelector('.od-icon-pause').style.display = state.paused ? 'none' : 'block';
            this.toggle.setAttribute('aria-label', state.paused ? 'Play' : 'Pause');
            this.toggle.title = state.paused ? 'Play' : 'Pause';
            this.timeline.max = Math.max(0, state.duration || 0);
            this.timeline.disabled = !state.duration;
            this.renderPosition();
            if (state.buffering) this.status.textContent = 'Buffering…';
            else if (this.status.textContent === 'Buffering…') this.status.textContent = '';
            if (!was_visible) this.timeline.focus({preventScroll:true});
        }

        renderPosition() {
            const value = Math.max(0, Math.min(this.draft ?? this.state.position ?? 0, this.state.duration || 0));
            this.timeline.value = value;
            this.timeline.setAttribute('aria-valuetext', formatDuration(value) + ' of ' + formatDuration(this.state.duration));
            this.root.style.setProperty('--transport-progress', (this.state.duration ? value / this.state.duration * 100 : 0) + '%');
            document.getElementById('od-transport-position').textContent = formatDuration(value);
        }

        async request(action, data) {
            try {
                await sendControl(action, data);
                this.status.textContent = '';
                return true;
            }
            catch (error) {
                this.status.textContent = errorMessage(error);
                return false;
            }
        }

        interact(action='show') {
            if (!this.state.active) return;
            return this.request('playback.controls', {session_id:this.state.session_id, action:action});
        }

        preview(position) {
            if (!this.state.duration) return;
            const now = Date.now();
            if (this.draft === null || now - this.last_interaction > 2000) {
                this.interact('hold');
                this.last_interaction = now;
            }
            this.pending_until = 0;
            this.draft = Math.max(0, Math.min(position, this.state.duration));
            this.renderPosition();
        }

        async commit() {
            if (this.draft === null) return;
            const session_id = this.state.session_id;
            this.pending_until = Date.now() + 15000;
            if (!await this.request('playback.seek', {session_id:session_id, position:this.draft})) {
                this.draft = null;
                this.pending_until = 0;
                this.renderPosition();
            }
        }

        transport(action, arguments_={}) {
            this.draft = null;
            this.pending_until = 0;
            return this.request(action, arguments_);
        }

        onKeydown(event) {
            if (!this.state.active || this.state.menu_visible) return;
            const action = navigationAction(event);
            if (!['navigation.left','navigation.right','navigation.up','navigation.down','navigation.select','navigation.back','playback.play_pause'].includes(action)) return;
            event.preventDefault();
            event.stopImmediatePropagation();
            const index = this.buttons.indexOf(document.activeElement);
            if (action === 'navigation.back') {
                this.draft = null;
                this.interact('hide');
            }
            else if (action === 'navigation.up') this.buttons[1].focus({preventScroll:true});
            else if (action === 'navigation.down') this.timeline.focus({preventScroll:true});
            else if (action === 'navigation.left' || action === 'navigation.right') {
                const direction = action === 'navigation.left' ? -1 : 1;
                if (index >= 0) this.buttons[Math.max(0, Math.min(index + direction, 2))].focus({preventScroll:true});
                else this.preview((this.draft ?? this.state.position ?? 0) + direction * 10);
            }
            else if (action === 'playback.play_pause') this.transport('playback.play_pause');
            else if (index >= 0) this.buttons[index].click();
            else if (action === 'navigation.select' && this.draft !== null) this.commit();
            else this.transport('playback.play_pause');
        }

        start() {
            this.abort = new AbortController();
            const options = {signal:this.abort.signal};
            window.addEventListener('fs42-playback-state', this.onState, options);
            document.addEventListener('keydown', this.onKeydown, {...options, capture:true});
            this.bindings = new ControlBindings(this.root, {onControl:(action, arguments_)=>this.transport(action, arguments_),
                onError:error=>{this.status.textContent=errorMessage(error)}});
            this.timeline.addEventListener('input', () => this.preview(Number(this.timeline.value)), options);
            this.timeline.addEventListener('change', () => this.commit(), options);
            this.root.addEventListener('pointermove', () => {
                if (Date.now() - this.last_interaction > 2000) {
                    this.last_interaction = Date.now();
                    this.interact(this.draft === null ? 'show' : 'hold');
                }
            }, options);
        }

        destroy() {
            this.bindings?.destroy();
            this.abort?.abort();
        }
    }

    self.setup = function() {
        self.instance?.destroy();
        self.instance = new PlaybackControls();
        self.instance.start();
    };
    return self;
})();
