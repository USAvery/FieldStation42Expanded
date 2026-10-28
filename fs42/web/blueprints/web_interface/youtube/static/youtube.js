/* This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0. */
window.app = window.app || {};
app.web_interface = app.web_interface || {};
app.web_interface.youtube = (function() {
    let self = {};
    let status = null;
    let list = null;

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
        if (!result.channels.length) status.textContent = 'No YouTube channels added yet.';
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

    self.setup = async function() {
        status = document.getElementById('youtube-status');
        list = document.getElementById('youtube-channels');
        document.getElementById('youtube-add-form').addEventListener('submit', self.addChannel);
        try {await self.loadChannels()}
        catch (error) {status.textContent = errorMessage(error)}
    };
    return self;
})();
