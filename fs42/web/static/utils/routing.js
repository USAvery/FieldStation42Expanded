/* This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0. */
window.app = window.app || {};
app.utils = app.utils || {};
app.utils.routing = (function() {
    let self = {};
    const config = window.fs42Routes || {root: '', paths: {}, endpoints: {}};
    const patterns = Object.entries(config.paths).sort(function(a, b) {
        return (a[0].match(/\{/g) || []).length - (b[0].match(/\{/g) || []).length || b[0].length - a[0].length;
    }).map(function(entry) {
        const names = [];
        const chunks = entry[0].split(/(\{[^}]+\})/).map(function(part) {
            if (part.startsWith('{')) {
                const name = part.slice(1, -1);
                names.push(name);
                return name === 'path' ? '(.+)' : '([^/]+)';
            }
            return part.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        });
        return {pattern: new RegExp('^' + chunks.join('') + '$'), path: entry[1], names: names};
    });

    /** Generate a named endpoint URL or resolve an existing path through the route map. */
    self.urlFor = function(endpoint, values = {}) {
        if (config.endpoints[endpoint]) {
            return config.endpoints[endpoint].replace(/\{([^}]+)\}/g, function(match, name) {
                if (values[name] === undefined) throw new Error('Missing route parameter: ' + name);
                return name === 'path' ? String(values[name]).split('/').map(encodeURIComponent).join('/') : encodeURIComponent(values[name]);
            });
        }
        if (/^(https?:|data:|blob:|#)/.test(endpoint)) return endpoint;
        const split = endpoint.search(/[?#]/);
        const path = split < 0 ? endpoint : endpoint.slice(0, split);
        const suffix = split < 0 ? '' : endpoint.slice(split);
        for (const route of patterns) {
            const match = route.pattern.exec(path);
            if (match) {
                let mounted = route.path;
                route.names.forEach((name, index) => { mounted = mounted.replace('{' + name + '}', match[index + 1]); });
                return mounted + suffix;
            }
        }
        if (path.startsWith('/') && config.root && path !== config.root && !path.startsWith(config.root + '/')) {
            return config.root + endpoint;
        }
        return endpoint;
    };

    /** Fetch a registered resource and preserve structured server error information. */
    self.fetch = async function(endpoint, options = {}) {
        const response = await window.fetch(self.urlFor(endpoint), options);
        if (!response.ok) {
            let body;
            try { body = await response.json(); } catch (_) { body = {}; }
            const error = new Error('Request failed (' + response.status + ')');
            error.status = response.status;
            error.detail = body.detail || body.message || body.error || error.message;
            throw error;
        }
        return response;
    };

    /** Send an API request and return its decoded result to a promise and optional callback. */
    self.ajaxEndpoint = async function(method, endpoint, data, callback) {
        if (typeof data === 'function') { callback = data; data = undefined; }
        const options = {method: method};
        if (data !== undefined) {
            options.headers = {'Content-Type': 'application/json'};
            options.body = JSON.stringify(data);
        }
        const path = config.endpoints[endpoint] || endpoint.startsWith('/') ? endpoint : '/' + endpoint;
        const response = await self.fetch(path, options);
        const result = response.status === 204 ? null : await response.json();
        if (callback) callback(result);
        return result;
    };
    self.get = (endpoint, callback) => self.ajaxEndpoint('GET', endpoint, undefined, callback);
    self.post = (endpoint, data, callback) => self.ajaxEndpoint('POST', endpoint, data, callback);
    self.put = (endpoint, data, callback) => self.ajaxEndpoint('PUT', endpoint, data, callback);
    self.delete = (endpoint, callback) => self.ajaxEndpoint('DELETE', endpoint, undefined, callback);
    return self;
})();
window.fs42Api = app.utils.routing;
