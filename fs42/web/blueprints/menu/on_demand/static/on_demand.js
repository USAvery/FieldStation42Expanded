/*
This Source Code Form is subject to the Mozilla Public License, v. 2.0.
See https://mozilla.org/MPL/2.0/.
*/
window.app = window.app || {};
app.menu = app.menu || {};
app.menu.on_demand = (function() {
    let self = {};

    let options = null;
    let navigation = null;
    let selection = null;
    let status = null;
    let search = null;
    let query_input = null;
    let details = null;
    let menu = null;
    let listing_items = new Map();
    let view = {type: 'home', title: 'Top Picks'};
    let history = [];
    let selected_index = 0;
    let request_id = 0;
    let playing = false;

    /**
     * Return the selectable menu and navigation buttons in visual order
     */
    self.getButtons = function() {
        return Array.from(document.querySelectorAll('#od-options button, #od-navigation button'));
    };
    /**
     * Highlight a choice and describe it in the upper information panel
     */
    self.selectChoice = function(index) {
        const buttons = self.getButtons();
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
        if (listing_items.has(button)) self.updateDetails(listing_items.get(button));
        if (view.type === 'titles' && button.parentElement === options) {
            const row = button.getBoundingClientRect();
            const viewport = options.getBoundingClientRect();
            if (row.top < viewport.top) options.scrollTop += row.top - viewport.top;
            else if (row.bottom > viewport.bottom) options.scrollTop += row.bottom - viewport.bottom;
        }
    };
    /**
     * Create a text-only menu button with matching pointer and remote behavior
     */
    self.addChoice = function(parent, title, action, description=title) {
        const button = document.createElement('button');
        button.type = 'button';
        button.textContent = title;
        button.dataset.description = description;
        if (parent === options) {
            button.className = 'od-choice';
        }
        button.addEventListener('pointermove', function() {
            self.selectChoice(self.getButtons().indexOf(button));
        });
        button.addEventListener('focus', function() {
            const index = self.getButtons().indexOf(button);
            if (index !== selected_index) {
                self.selectChoice(index);
            }
        });
        button.addEventListener('click', action);
        parent.appendChild(button);
        return button;
    };
    /**
     * Return to the previous library screen, or close the overlay at the root
     */
    self.goBack = function(closeAtRoot=true) {
        if (playing) {
            return;
        }
        if (history.length) {
            view = history.pop();
            self.renderView();
        }
        else if (closeAtRoot) {
            apiPost('api.player.close_menu').catch(function(error) {
                console.error('Could not close On Demand:', error);
            });
        }
    };
    /**
     * Preserve the current screen before opening a category, title, or search
     */
    self.openView = function(next) {
        view.selected = selected_index;
        history.push(view);
        view = next;
        self.renderView();
    };
    /**
     * Display a failed request with an explicit retry and working back navigation
     */
    self.showError = function(error, retry) {
        status.textContent = error.detail || 'Unable to load the library. Please try again.';
        options.replaceChildren();
        self.addChoice(options, 'Try Again', retry);
        self.selectChoice(0);
    };
    /**
     * Ask the current player to play the selected catalog record exactly once
     */
    self.playTitle = function(item) {
        if (playing) {
            return;
        }
        playing = true;
        status.textContent = 'Starting ' + item.title + '…';
        const endpoint = item.source === 'youtube'
            ? urlFor('api.youtube.play_upload', {channel_id:item.channel_id, video_id:item.id})
            : urlFor('api.on_demand.play_title', {entry_id:item.id});
        apiPost(endpoint, {})
            .catch(function(error) {
                status.textContent = error.detail || 'Playback could not start. Please try again.';
                playing = false;
            });
    };
    /**
     * Describe the highlighted title in the shared top panel
     */
    self.updateDetails = function(item) {
        details.hidden = false;
        document.getElementById('od-title').textContent = item.title;
        const minutes = item.duration ? Math.round(item.duration / 60) + ' min' : '';
        const episode = item.kind === 'episode' && item.season != null && item.episode != null
            ? 'Season ' + item.season + ', Episode ' + item.episode : '';
        document.getElementById('od-meta').textContent = [item.year, minutes, episode, item.network]
            .filter(Boolean).join('  •  ');
        document.getElementById('od-description').textContent = item.description || '';
    };

    /** Show playback actions only after the viewer opens a title. */
    self.showDetails = function() {
        const item = view.item;
        self.updateDetails(item);
        self.addChoice(options, 'Play', function() { self.playTitle(item); }, item.title);
        self.selectChoice(0);
    };
    /**
     * Render a remote-operated search keyboard alongside a normal text field
     */
    self.showSearch = function() {
        search.hidden = false;
        query_input.value = view.query || '';
        options.classList.add('od-keyboard');
        const keys = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'.split('');
        keys.concat(['Space', 'Delete', 'Clear', 'Search']).forEach(function(key) {
            self.addChoice(options, key, function() {
                if (key === 'Search') {
                    self.submitSearch();
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
        self.selectChoice(0);
    };
    /**
     * Open literal title-search results without searching on every keystroke
     */
    self.submitSearch = function() {
        view.query = query_input.value.trim();
        if (!view.query) {
            status.textContent = 'Enter a title to search.';
            return;
        }
        self.openView({type: 'titles', title: 'Search: ' + view.query, category: 'search', query: view.query, page: 0});
    };
    /**
     * Fetch one result page and discard responses belonging to a screen already left
     */
    self.showTitles = function(token) {
        status.textContent = 'Loading titles…';
        const params = new URLSearchParams({category: view.category, page: view.page || 0});
        if (view.query) {
            params.set('query', view.query);
        }
        if (view.channel) {
            params.set('channel', view.channel);
        }
        const endpoint = view.youtube_channel
            ? urlFor('api.youtube.get_uploads', {channel_id:view.youtube_channel, page:view.page || 0})
            : urlFor('api.on_demand.get_titles') + '?' + params.toString();
        apiGet(endpoint)
            .then(function(result) {
                if (token !== request_id) {
                    return;
                }
                status.textContent = result.total ? '' : 'No titles found. Choose another category or search.';
                result.items.forEach(function(item) {
                    const button = self.addChoice(options, item.title, function() {
                        self.openView({type: 'details', title: item.title, item: item});
                    });
                    listing_items.set(button, item);
                });
                if (result.page > 0) {
                    self.addChoice(navigation, '◀ Previous', function() { view.page--; self.renderView(); });
                }
                if ((result.page + 1) * result.page_size < result.total) {
                    self.addChoice(navigation, 'More Choices ▼', function() { view.page = result.page + 1; view.selected = 0; self.renderView(); });
                }
                self.selectChoice(view.selected || 0);
            })
            .catch(function(error) {
                if (token === request_id) {
                    self.showError(error, self.renderView);
                }
            });
    };
    /**
     * Render the current menu state without starting media or background animation
     */
    self.renderView = function() {
        const token = ++request_id;
        options.replaceChildren();
        options.scrollTop = 0;
        listing_items.clear();
        navigation.replaceChildren();
        const listings = view.type === 'titles' || view.type === 'details';
        document.getElementById('od-wrapper').classList.toggle('od-listings', listings);
        document.getElementById('od-heading').hidden = listings;
        document.getElementById('od-listings-heading').hidden = !listings;
        document.getElementById('od-listings-title').textContent = view.title;
        options.classList.remove('od-keyboard');
        details.hidden = true;
        search.hidden = true;
        status.textContent = '';
        selection.textContent = view.title;
        if (view.type === 'details') {
            self.showDetails();
        }
        else if (view.type === 'search') {
            self.showSearch();
        }
        else if (view.type === 'titles') {
            self.showTitles(token);
            self.selectChoice(0);
        }
        else if (view.type === 'youtube') {
            self.showYouTubeChannels(token);
        }
        else if (view.type === 'channels') {
            const page = view.page || 0;
            menu.channels.slice(page * 10, page * 10 + 10).forEach(function(channel) {
                self.addChoice(options, channel.title, function() {
                    self.openView({type: 'titles', title: channel.title, category: 'all', channel: channel.id, page: 0});
                });
            });
            if (page > 0) {
                self.addChoice(navigation, '◀ Previous', function() { view.page--; self.renderView(); });
            }
            if ((page + 1) * 10 < menu.channels.length) {
                self.addChoice(navigation, 'More Choices ▼', function() { view.page = page + 1; self.renderView(); });
            }
            if (!menu.channels.length) {
                status.textContent = 'No cataloged channels are available.';
            }
            self.selectChoice(view.selected || 0);
        }
        else {
            menu.categories.forEach(function(category) {
                self.addChoice(options, category.title, function() {
                    const type = ['search', 'channels', 'youtube'].includes(category.id) ? category.id : 'titles';
                    self.openView({type: type, title: category.title, category: category.id, page: 0});
                });
            });
            self.selectChoice(view.selected || 0);
        }
    };
    /**
     * Load menu choices once and retain an explicit retry if the server is unavailable
     */
    self.showYouTubeChannels = function(token) {
        status.textContent = 'Loading YouTube channels…';
        apiGet('api.youtube.get_channels').then(function(result) {
            if (token !== request_id) return;
            status.textContent = result.channels.length ? '' : 'Add YouTube channels from the web console to see them here.';
            const page = view.page || 0;
            result.channels.slice(page * 10, page * 10 + 10).forEach(function(channel) {
                self.addChoice(options, channel.title, function() {
                    self.openView({type:'titles', title:channel.title, youtube_channel:channel.id, page:0});
                });
            });
            if (page > 0) self.addChoice(navigation, 'Previous', function() {view.page--; self.renderView()});
            if ((page + 1) * 10 < result.channels.length) {
                self.addChoice(navigation, 'More Choices', function() {view.page++; view.selected=0; self.renderView()});
            }
            self.selectChoice(view.selected || 0);
        }).catch(function(error) {
            if (token === request_id) self.showError(error, self.renderView);
        });
    };

    self.loadMenu = function() {
        status.textContent = 'Loading library…';
        apiGet('api.on_demand.get_menu')
            .then(function(result) { menu = result; self.renderView(); })
            .catch(function(error) {
                navigation.replaceChildren();
                self.showError(error, self.loadMenu);
            });
    };
    /**
     * Move among category buttons, listing rows, search keys, and navigation
     */
    self.onKeydown = function(event) {
        if (document.body.classList.contains('on-demand-playing')) return;
        if (event.target === query_input) {
            if (event.key === 'Enter') {
                event.preventDefault();
                self.submitSearch();
            }
            else if (event.key === 'Escape' || event.key === 'Backspace') {
                event.preventDefault();
                self.goBack();
            }
            else if (event.key === 'ArrowDown') {
                event.preventDefault();
                self.selectChoice(0);
            }
            return;
        }
        const keys = ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Enter', 'Escape', 'Backspace', 'PageUp', 'PageDown'];
        if (!keys.includes(event.key)) {
            return;
        }
        event.preventDefault();
        const buttons = self.getButtons();
        if (event.key === 'Escape' || event.key === 'Backspace' || event.key === 'PageUp') {
            self.goBack(event.key !== 'PageUp');
            return;
        }
        if (event.key === 'Enter') {
            if (buttons[selected_index]) {
                buttons[selected_index].click();
            }
            return;
        }
        const columns = view.type === 'search' ? 8 : (view.type === 'titles' || view.type === 'details' ? 1 : 2);
        const count = options.childElementCount;
        if (event.key === 'ArrowDown') {
            self.selectChoice(selected_index < count ? Math.min(count, selected_index + columns) : selected_index);
        }
        else if (event.key === 'ArrowUp') {
            self.selectChoice(selected_index >= count ? Math.max(0, count - columns) : selected_index - columns);
        }
        else if (event.key === 'PageDown') {
            self.selectChoice(buttons.length - 1);
        }
        else {
            self.selectChoice(selected_index + (event.key === 'ArrowRight' ? 1 : -1));
        }
    };

    /** Initialize the page and bind its controls. */
    /** Handle fs42-guide-show. */
    self.onFs42GuideShow = function() {
        playing = false;
        status.textContent = '';
    };

    self.setup = function() {
        options = document.getElementById('od-options');
        navigation = document.getElementById('od-navigation');
        selection = document.getElementById('od-selection');
        status = document.getElementById('od-status');
        search = document.getElementById('od-search');
        query_input = document.getElementById('od-query');
        details = document.getElementById('od-details');
        document.addEventListener('keydown', self.onKeydown);
        window.addEventListener('fs42-guide-show', self.onFs42GuideShow);
        self.loadMenu();
    };
    return self;
})();
