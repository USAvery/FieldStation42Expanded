/* This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0. */

// Globals
let $ROOT_PATH = window.$ROOT_PATH || '';
let $ROUTES = undefined;
let $PATHS = [];
let routesRequest = undefined;

/**
 * Determine whether a given URL is internal
 * @param url {string} a URL
 * @returns   {boolean} whether the URL belongs to this application origin
 */
function isInternal(url) {
    return new URL(url, window.location.href).origin === window.location.origin;
}

/**
 * Carry out a GET method to a URL and pass its text to an optional callback
 * @param url      {string} the URL or endpoint
 * @param callback {function} the callback function
 * @param method   {string} the HTTP method
 * @returns        {Promise} the response text
 */
function ajaxURL(url, callback=undefined, method='GET') {
    return fetchURL(url, {method: method}).then(res => res.text()).then(res => {
        if (callback !== undefined) callback(res);
        return res;
    });
}

/**
 * Carry out a POST method with JSON data or the main form's fields
 * @param url      {string} the URL or endpoint
 * @param data     {Object} optional JSON data; omit to submit main-form
 * @param callback {function} the callback function
 * @param type     {string} the expected response type ('text' or 'json')
 * @returns        {Promise} the decoded response
 */
function ajaxPost(url, data=undefined, callback=undefined, type='text') {
    // Shift args if data was omitted
    if (typeof data === 'function') {
        type = typeof callback === 'string' ? callback : type;
        callback = data;
        data = undefined;
    }

    // Create fetch init
    let fetch_init = {method: 'POST'};
    if (data !== undefined) {
        fetch_init.headers = {'Content-Type': 'application/json'};
        fetch_init.body = JSON.stringify(data);
    }
    else {
        const form = document.getElementById('main-form');
        if (!form) return Promise.reject(new Error('Cannot submit: main-form was not found.'));
        fetch_init.body = new FormData(form);
    }

    return fetchURL(url, fetch_init).then(res => {
        if (res.status === 204) return type === 'text' ? '' : null;
        return type === 'text' ? res.text() : res.json();
    }).then(res => {
        if (callback !== undefined) callback(res);
        return res;
    });
}

/**
 * Carry out a GET method to an endpoint after its routes have loaded
 * @param endpoint {string} the endpoint name
 * @param args     {object} path and query arguments
 * @param callback {function} the callback function receiving response text
 * @returns        {Promise} the response text
 */
function ajaxEndpoint(endpoint, args={}, callback=undefined) {
    return loadRoutes().then(() => ajaxURL(urlFor(endpoint, args), callback));
}

/**
 * Create an encoded query string from an arguments object
 * @param args {object} query arguments; array values become repeated parameters
 * @returns    {string} the query string, including its leading question mark
 */
function convertArgsToStr(args={}) {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(args)) {
        if (value === undefined || value === null) continue;
        for (const item of Array.isArray(value) ? value : [value]) params.append(key, item);
    }
    const query = params.toString();
    return query ? '?' + query : '';
}

/**
 * Split an absolute or relative URL into its base URL and query arguments
 * @param url {string} the entire URL
 * @returns   {Array} the base URL and arguments
 */
function splitUrl(url) {
    const parsed = new URL(url, window.location.href);
    let args = {};
    for (const [key, value] of parsed.searchParams.entries()) {
        if (Object.prototype.hasOwnProperty.call(args, key)) {
            args[key] = [].concat(args[key], value);
        }
        else Object.defineProperty(args, key, {value: value, enumerable: true, writable: true});
    }
    return [url.split(/[?#]/)[0], args];
}

/**
 * Get an endpoint URL, fill its path parameters, and append remaining query arguments
 * @param endpoint {string} the endpoint name or an existing application URL
 * @param args     {object} path and query arguments
 * @param filename {string} an optional static filename
 * @returns        {string} the encoded URL
 */
function urlFor(endpoint, args={}, filename='') {
    const error_msg = 'Cannot retrieve url for "' + endpoint + '". ';
    if (typeof $ROUTES === 'undefined') throw new Error(error_msg + 'Please wait for routes to load.');

    let values = {...args};
    const route = $ROUTES.find(item => item.endpoint === endpoint);
    let url;
    if (route) {
        if (filename && route.url.includes('{path}') && values.path === undefined) {
            values.path = filename;
            filename = '';
        }
        url = route.url.replace(/\{([^}]+)\}/g, function(match, name) {
            if (values[name] === undefined) throw new Error(error_msg + 'Missing path argument: ' + name);
            const value = values[name];
            delete values[name];
            return name === 'path' ? String(value).split('/').map(encodeURIComponent).join('/') : encodeURIComponent(value);
        });
    }
    else if (/^(?:api|web_interface|menu|widgets)\.[^/?#]+$/.test(endpoint)) {
        throw new Error(error_msg + 'Endpoint not found in routes.');
    }
    else url = resolveRouteURL(endpoint);

    if (filename) url = url.replace(/\/$/, '') + '/' + filename.split('/').map(encodeURIComponent).join('/');
    const fragment = url.indexOf('#');
    const hash = fragment < 0 ? '' : url.slice(fragment);
    if (fragment >= 0) url = url.slice(0, fragment);
    const query = convertArgsToStr(values);
    return url + (url.includes('?') && query ? '&' + query.slice(1) : query) + hash;
}

/** Resolve existing application paths through configured blueprint and deployment prefixes. */
function resolveRouteURL(url) {
    if (/^(https?:|data:|blob:|#|\/\/)/.test(url)) return url;
    const split = url.search(/[?#]/);
    const path = split < 0 ? url : url.slice(0, split);
    const suffix = split < 0 ? '' : url.slice(split);
    for (const route of $PATHS) {
        const match = route.pattern.exec(path);
        if (!match) continue;
        let mounted = route.url;
        route.args.forEach((name, index) => { mounted = mounted.replace('{' + name + '}', match[index + 1]); });
        return mounted + suffix;
    }
    if (path.startsWith('/') && $ROOT_PATH && path !== $ROOT_PATH && !path.startsWith($ROOT_PATH + '/')) {
        return $ROOT_PATH + url;
    }
    return url;
}

/** Load route information from the rendered page or the application's route endpoint. */
function loadRoutes() {
    if (typeof $ROUTES !== 'undefined') return Promise.resolve($ROUTES);
    if (routesRequest) return routesRequest;
    if (window.fs42Routes) {
        setRoutes(window.fs42Routes);
        return Promise.resolve($ROUTES);
    }
    routesRequest = window.fetch($ROOT_PATH + '/web/routes').then(decodeResponse).then(res => res.json()).then(data => {
        setRoutes(data);
        return $ROUTES;
    }).finally(() => { routesRequest = undefined; });
    return routesRequest;
}

/** Populate the common route list and compatibility path mappings. */
function setRoutes(data) {
    $ROOT_PATH = data.root || '';
    $ROUTES = Object.entries(data.endpoints).map(([endpoint, url]) => ({endpoint: endpoint, url: url}));
    $PATHS = Object.entries(data.paths).sort(function(a, b) {
        return (a[0].match(/\{/g) || []).length - (b[0].match(/\{/g) || []).length || b[0].length - a[0].length;
    }).map(function(entry) {
        const args = [];
        const parts = entry[0].split(/(\{[^}]+\})/).map(function(part) {
            if (part.startsWith('{')) {
                const name = part.slice(1, -1);
                args.push(name);
                return name === 'path' ? '(.+)' : '([^/]+)';
            }
            return part.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        });
        return {pattern: new RegExp('^' + parts.join('') + '$'), url: entry[1], args: args};
    });
}

/** Navigate to a URL, allowing the browser to release the current page's players and timers. */
function redirect(url, event=undefined) {
    if (event) event.preventDefault();
    window.location.assign(isInternal(url) ? urlFor(url) : url);
}

/** Retrieve a page title without modifying the current document. */
function getPageTitle(url, callback=undefined) {
    return ajaxURL(url).then(res => {
        const title = new DOMParser().parseFromString(res, 'text/html').title;
        if (callback !== undefined) callback(title);
        return title;
    });
}

/** Preserve structured API errors while leaving presentation to the caller. */
async function decodeResponse(response) {
    if (response.ok) return response;
    let body;
    try { body = await response.json(); } catch (_) { body = {}; }
    const error = new Error('Request failed (' + response.status + ')');
    error.status = response.status;
    error.detail = body.detail || body.message || body.error || error.message;
    throw error;
}

/** Fetch a registered resource and return its response object. */
function fetchURL(endpoint, options={}) {
    return loadRoutes().then(() => window.fetch(urlFor(endpoint), options)).then(decodeResponse);
}

/** Send a JSON API request and return its decoded result. */
function requestJSON(method, endpoint, data=undefined, callback=undefined) {
    if (typeof data === 'function') { callback = data; data = undefined; }
    return loadRoutes().then(() => {
        const named = $ROUTES.some(route => route.endpoint === endpoint);
        const url = named || /^(?:\/|https?:)/.test(endpoint) ? endpoint : '/' + endpoint;
        let options = {method: method};
        if (data !== undefined) {
            options.headers = {'Content-Type': 'application/json'};
            options.body = JSON.stringify(data);
        }
        return fetchURL(url, options);
    }).then(res => res.status === 204 ? null : res.json()).then(res => {
        if (callback !== undefined) callback(res);
        return res;
    });
}

// JSON adapters used by the console and Pi pages
function apiGet(endpoint, callback=undefined) {
    return requestJSON('GET', endpoint, undefined, callback);
}
function apiPost(endpoint, data, callback=undefined) {
    return requestJSON('POST', endpoint, data, callback);
}
function apiPut(endpoint, data, callback=undefined) {
    return requestJSON('PUT', endpoint, data, callback);
}
function apiDelete(endpoint, callback=undefined) {
    return requestJSON('DELETE', endpoint, undefined, callback);
}

/** Initialize the route data before page setup runs. */
function routingInit() {
    return loadRoutes();
}

routingInit().catch(error => console.error('Could not load routes:', error));
