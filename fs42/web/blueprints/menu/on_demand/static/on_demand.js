/*
This Source Code Form is subject to the Mozilla Public License, v. 2.0.
See https://mozilla.org/MPL/2.0/.
*/
window.app = window.app || {};
app.menu = app.menu || {};
app.menu.on_demand = (function() {
    let self = {};

    /**
     * Connect library browsing, remote navigation, and single-title playback
     */
    self.setup = function() {
        const options = document.getElementById('od-options');
        const navigation = document.getElementById('od-navigation');
        const selection = document.getElementById('od-selection');
        const status = document.getElementById('od-status');
        const search = document.getElementById('od-search');
        const query_input = document.getElementById('od-query');
        const details = document.getElementById('od-details');
        let menu = null;
        let view = {type: 'home', title: 'Top Picks'};
        let history = [];
        let selected_index = 0;
        let request_id = 0;
        let playing = false;

        /**
         * Return the selectable menu and navigation buttons in visual order
         */
        function getButtons() {
            return Array.from(document.querySelectorAll('#od-options button, #od-navigation button'));
        }

        /**
         * Highlight a choice and describe it in the upper information panel
         */
        function selectChoice(index) {
            const buttons = getButtons();
            if (!buttons.length) {
                return;
            }
            selected_index = Math.max(0, Math.min(index, buttons.length - 1));
            buttons.forEach(function(button, i) {
                button.classList.toggle('is-selected', i === selected_index);
                button.tabIndex = i === selected_index ? 0 : -1;
            });
            const button = buttons[selected_index];
            button.focus({preventScroll: true});
            selection.textContent = button.dataset.description || view.title;
        }

        /**
         * Create a text-only menu button with matching pointer and remote behavior
         */
        function addChoice(parent, title, action, description=title) {
            const button = document.createElement('button');
            button.type = 'button';
            button.textContent = title;
            button.dataset.description = description;
            if (parent === options) {
                button.className = 'od-choice';
            }
            button.addEventListener('pointermove', function() {
                selectChoice(getButtons().indexOf(button));
            });
            button.addEventListener('focus', function() {
                const index = getButtons().indexOf(button);
                if (index !== selected_index) {
                    selectChoice(index);
                }
            });
            button.addEventListener('click', action);
            parent.appendChild(button);
        }

        /**
         * Return to a previous library screen or to the television listings
         */
        function goBack() {
            if (playing) {
                return;
            }
            if (history.length) {
                view = history.pop();
                renderView();
            }
            else {
                window.location.href = window.fs42Api.urlFor('/static/customguide/customguide.html');
            }
        }

        /**
         * Preserve the current screen before opening a category, title, or search
         */
        function openView(next) {
            view.selected = selected_index;
            history.push(view);
            view = next;
            renderView();
        }

        /**
         * Display a failed request with an explicit retry and working back navigation
         */
        function showError(error, retry) {
            status.textContent = error.detail || 'Unable to load the library. Please try again.';
            options.replaceChildren();
            addChoice(options, 'Try Again', retry);
            selectChoice(0);
        }

        /**
         * Ask the current player to play the selected catalog record exactly once
         */
        function playTitle(item) {
            if (playing) {
                return;
            }
            playing = true;
            status.textContent = 'Starting ' + item.title + '…';
            window.fs42Api.post(window.fs42Api.urlFor('api.on_demand.play_title', {entry_id: item.id}), {})
                .catch(function(error) {
                    status.textContent = error.detail || 'Playback could not start. Please try again.';
                    playing = false;
                });
        }

        /**
         * Render the selected title's metadata and its explicit playback action
         */
        function showDetails() {
            const item = view.item;
            details.hidden = false;
            document.getElementById('od-title').textContent = item.title;
            const minutes = Math.round(item.duration / 60);
            const episode = item.kind === 'episode' && item.season != null && item.episode != null
                ? 'Season ' + item.season + ', Episode ' + item.episode : '';
            document.getElementById('od-meta').textContent = [item.year, minutes + ' min', episode, item.network]
                .filter(Boolean).join('  •  ');
            document.getElementById('od-description').textContent = item.description;
            addChoice(options, 'Play', function() { playTitle(item); }, item.title);
            addChoice(options, 'Back', goBack, 'Back to titles');
            selectChoice(0);
        }

        /**
         * Render a remote-operated search keyboard alongside a normal text field
         */
        function showSearch() {
            search.hidden = false;
            query_input.value = view.query || '';
            options.classList.add('od-keyboard');
            const keys = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'.split('');
            keys.concat(['Space', 'Delete', 'Clear', 'Search']).forEach(function(key) {
                addChoice(options, key, function() {
                    if (key === 'Search') {
                        submitSearch();
                        return;
                    }
                    if (key === 'Delete') {
                        query_input.value = query_input.value.slice(0, -1);
                    }
                    else if (key === 'Clear') {
                        query_input.value = '';
                    }
                    else if (query_input.value.length < 200) {
                        query_input.value += key === 'Space' ? ' ' : key;
                    }
                    view.query = query_input.value;
                }, 'Search');
            });
            selectChoice(0);
        }

        /**
         * Open literal title-search results without searching on every keystroke
         */
        function submitSearch() {
            view.query = query_input.value.trim();
            if (!view.query) {
                status.textContent = 'Enter a title to search.';
                return;
            }
            openView({type: 'titles', title: 'Search: ' + view.query, category: 'search', query: view.query, page: 0});
        }

        /**
         * Fetch one result page and discard responses belonging to a screen already left
         */
        function showTitles(token) {
            status.textContent = 'Loading titles…';
            const params = new URLSearchParams({category: view.category, page: view.page || 0});
            if (view.query) {
                params.set('query', view.query);
            }
            if (view.channel) {
                params.set('channel', view.channel);
            }
            window.fs42Api.get(window.fs42Api.urlFor('api.on_demand.get_titles') + '?' + params.toString())
                .then(function(result) {
                    if (token !== request_id) {
                        return;
                    }
                    status.textContent = result.total ? '' : 'No titles found. Choose another category or search.';
                    result.items.forEach(function(item) {
                        addChoice(options, item.title, function() {
                            openView({type: 'details', title: item.title, item: item});
                        });
                    });
                    if (result.page > 0) {
                        addChoice(navigation, '◀ Previous', function() { view.page--; renderView(); });
                    }
                    if ((result.page + 1) * result.page_size < result.total) {
                        addChoice(navigation, 'More Choices ▼', function() { view.page = result.page + 1; view.selected = 0; renderView(); });
                    }
                    selectChoice(view.selected || 0);
                })
                .catch(function(error) {
                    if (token === request_id) {
                        showError(error, renderView);
                    }
                });
        }

        /**
         * Render the current menu state without starting media or background animation
         */
        function renderView() {
            const token = ++request_id;
            options.replaceChildren();
            navigation.replaceChildren();
            options.classList.remove('od-keyboard');
            details.hidden = true;
            search.hidden = true;
            status.textContent = '';
            selection.textContent = view.title;
            addChoice(navigation, history.length ? '◀ Back' : '◀ TV Listings', goBack);
            if (view.type === 'details') {
                showDetails();
            }
            else if (view.type === 'search') {
                showSearch();
            }
            else if (view.type === 'titles') {
                showTitles(token);
                selectChoice(0);
            }
            else if (view.type === 'channels') {
                const page = view.page || 0;
                menu.channels.slice(page * 10, page * 10 + 10).forEach(function(channel) {
                    addChoice(options, channel.title, function() {
                        openView({type: 'titles', title: channel.title, category: 'all', channel: channel.id, page: 0});
                    });
                });
                if (page > 0) {
                    addChoice(navigation, '◀ Previous', function() { view.page--; renderView(); });
                }
                if ((page + 1) * 10 < menu.channels.length) {
                    addChoice(navigation, 'More Choices ▼', function() { view.page = page + 1; renderView(); });
                }
                if (!menu.channels.length) {
                    status.textContent = 'No cataloged channels are available.';
                }
                selectChoice(view.selected || 0);
            }
            else {
                menu.categories.forEach(function(category) {
                    addChoice(options, category.title, function() {
                        const type = category.id === 'search' || category.id === 'channels' ? category.id : 'titles';
                        openView({type: type, title: category.title, category: category.id, page: 0});
                    });
                });
                selectChoice(view.selected || 0);
            }
        }

        /**
         * Load menu choices once and retain an explicit retry if the server is unavailable
         */
        function loadMenu() {
            status.textContent = 'Loading library…';
            window.fs42Api.get('api.on_demand.get_menu')
                .then(function(result) { menu = result; renderView(); })
                .catch(function(error) {
                    navigation.replaceChildren();
                    addChoice(navigation, '◀ TV Listings', goBack);
                    showError(error, loadMenu);
                });
        }

        /**
         * Move among the two-column menu, search keys, and footer with remote-control arrows
         */
        function onKeydown(event) {
            if (event.target === query_input) {
                if (event.key === 'Enter') {
                    event.preventDefault();
                    submitSearch();
                }
                else if (event.key === 'ArrowDown' || event.key === 'Escape') {
                    event.preventDefault();
                    selectChoice(0);
                }
                return;
            }
            const keys = ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Enter', 'Escape', 'Backspace', 'PageUp', 'PageDown'];
            if (!keys.includes(event.key)) {
                return;
            }
            event.preventDefault();
            const buttons = getButtons();
            if (event.key === 'Escape' || event.key === 'Backspace' || event.key === 'PageUp') {
                goBack();
                return;
            }
            if (event.key === 'Enter') {
                if (buttons[selected_index]) {
                    buttons[selected_index].click();
                }
                return;
            }
            const columns = view.type === 'search' ? 8 : 2;
            const count = options.childElementCount;
            if (event.key === 'ArrowDown') {
                selectChoice(selected_index < count ? Math.min(count, selected_index + columns) : selected_index);
            }
            else if (event.key === 'ArrowUp') {
                selectChoice(selected_index >= count ? Math.max(0, count - columns) : selected_index - columns);
            }
            else if (event.key === 'PageDown') {
                selectChoice(buttons.length - 1);
            }
            else {
                selectChoice(selected_index + (event.key === 'ArrowRight' ? 1 : -1));
            }
        }

        /**
         * Refresh the compact clock once per second without polling library or player state
         */
        function updateClock() {
            document.getElementById('od-clock').textContent = new Date().toLocaleTimeString('en-US', {
                hour: 'numeric', minute: '2-digit', hour12: true
            }).replace(' ', '').toLowerCase();
        }

        document.addEventListener('keydown', onKeydown);
        window.addEventListener('fs42-guide-show', function() {
            playing = false;
            status.textContent = '';
        });
        updateClock();
        setInterval(updateClock, 1000);
        loadMenu();
    };
    return self;
})();
