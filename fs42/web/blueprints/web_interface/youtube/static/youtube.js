/* This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0. */
window.app = window.app || {};
app.web_interface = app.web_interface || {};
app.web_interface.youtube = (function() {
    let self = {};
    let status = null;
    let list = null;
    let playlist_list = null;

    self.loadChannels = async function() {
        const result = await apiGet('api.youtube.get_channels');
        list.replaceChildren();
        result.channels.forEach(function(channel) {
            const row = document.createElement('li');
            const link = document.createElement('a');
            link.textContent = channel.title;
            link.href = channel.url;
            link.target = '_blank';
            link.rel = 'noopener noreferrer';
            const remove = document.createElement('button');
            remove.type = 'button';
            remove.className = 'pure-button';
            remove.textContent = 'Remove';
            remove.setAttribute('aria-label', 'Remove ' + channel.title);
            remove.addEventListener('click', function() {self.removeChannel(channel, remove)});
            row.append(link, remove);
            list.appendChild(row);
        });
        document.getElementById('youtube-channel-empty').textContent = result.channels.length
            ? '' : 'No YouTube channels added yet.';
    };

    self.loadPlaylists = async function() {
        const result = await apiGet('api.youtube.get_playlists');
        playlist_list.replaceChildren();
        result.playlists.forEach(function(playlist) {
            const row = document.createElement('li');
            const link = document.createElement('a');
            link.textContent = playlist.title;
            link.href = playlist.url;
            link.target = '_blank';
            link.rel = 'noopener noreferrer';
            const remove = document.createElement('button');
            remove.type = 'button';
            remove.className = 'pure-button';
            remove.textContent = 'Remove';
            remove.setAttribute('aria-label', 'Remove ' + playlist.title);
            remove.addEventListener('click', function() {self.removePlaylist(playlist, remove);});
            row.append(link, remove);
            playlist_list.appendChild(row);
        });
        if (!result.playlists.length) {
            document.getElementById('youtube-playlist-empty').textContent = 'No YouTube playlists added yet.';
        }
        else {
            document.getElementById('youtube-playlist-empty').textContent = '';
        }
    };

    self.addChannel = async function(event) {
        event.preventDefault();
        const input = document.getElementById('youtube-channel-url');
        const button = document.getElementById('youtube-add');
        button.disabled = true;
        status.textContent = 'Looking up channel…';
        try {
            const channel = await apiPost('api.youtube.add_channel', {url:input.value.trim()});
            await self.loadChannels();
            input.value = '';
            status.textContent = channel.title + ' added to On Demand.';
        }
        catch (error) {status.textContent = errorMessage(error)}
        finally {button.disabled = false}
    };

    self.removeChannel = async function(channel, button) {
        button.disabled = true;
        try {
            await apiDelete(urlFor('api.youtube.remove_channel', {channel_id:channel.id}));
            await self.loadChannels();
            status.textContent = channel.title + ' removed from On Demand.';
        }
        catch (error) {status.textContent = errorMessage(error); button.disabled = false}
    };

    self.addPlaylist = async function(event) {
        event.preventDefault();
        const input = document.getElementById('youtube-playlist-url');
        const button = document.getElementById('youtube-playlist-add');
        button.disabled = true;
        status.textContent = 'Looking up playlist…';
        try {
            const playlist = await apiPost('api.youtube.add_playlist', {url: input.value.trim()});
            await self.loadPlaylists();
            input.value = '';
            status.textContent = playlist.title + ' added to On Demand.';
        }
        catch (error) {
            status.textContent = errorMessage(error);
        }
        finally {
            button.disabled = false;
        }
    };

    self.removePlaylist = async function(playlist, button) {
        button.disabled = true;
        try {
            await apiDelete(urlFor('api.youtube.remove_playlist', {playlist_id: playlist.id}));
            await self.loadPlaylists();
            status.textContent = playlist.title + ' removed from On Demand.';
        }
        catch (error) {
            status.textContent = errorMessage(error);
            button.disabled = false;
        }
    };

    self.setup = async function() {
        status = document.getElementById('youtube-status');
        list = document.getElementById('youtube-channels');
        playlist_list = document.getElementById('youtube-playlists');
        document.getElementById('youtube-add-form').addEventListener('submit', self.addChannel);
        document.getElementById('youtube-playlist-form').addEventListener('submit', self.addPlaylist);
        try {
            await Promise.all([self.loadChannels(), self.loadPlaylists()]);
        }
        catch (error) {
            status.textContent = errorMessage(error);
        }
    };
    return self;
})();
