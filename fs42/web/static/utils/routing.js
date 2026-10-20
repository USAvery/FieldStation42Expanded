/*
This Source Code Form is subject to the Mozilla Public License, v. 2.0.
See https://mozilla.org/MPL/2.0/.
*/
window.app = window.app || {};
app.utils = app.utils || {};
app.utils.routing = (function () {
    let self = {};
    const base_url = window.location.protocol + '//' + window.location.hostname + ':4242';

    /**
     * Send an API request and pass the decoded result to an optional callback
     * @param method   {string}   the HTTP method
     * @param endpoint {string}   the API path without a leading slash
     * @param data     {object}   the optional request body
     * @param callback {function} the optional completion callback
     * @returns        {Promise} the decoded response
     */
    self.ajaxEndpoint = function (method, endpoint, data = undefined, callback = undefined) {
        if (typeof data === 'function') {
            callback = data;
            data = undefined;
        }

        // Build the request
        const options = {
            method: method
        };
        if (data !== undefined) {
            options.headers = {
                'Content-Type': 'application/json'
            };
            options.body = JSON.stringify(data);
        }

        // Decode the response and report API errors
        return fetch(base_url + '/' + endpoint, options)
            .then(function (response) {
                if (response.ok) {
                    return response.json();
                }
                return response
                    .json()
                    .catch(function () {
                        return {};
                    })
                    .then(function (body) {
                        const error = new Error(method + ' ' + endpoint + ' failed: ' + response.status);
                        error.detail = body.detail || body.message;
                        throw error;
                    });
            })
            .then(function (result) {
                if (callback !== undefined) {
                    callback(result);
                }
                return result;
            });
    };

    /**
     * Get an API resource
     * @param endpoint {string}   the API path
     * @param callback {function} the optional completion callback
     */
    self.get = function (endpoint, callback = undefined) {
        return self.ajaxEndpoint('GET', endpoint, undefined, callback);
    };

    /**
     * Create an API resource
     * @param endpoint {string}   the API path
     * @param data     {object}   the request body
     * @param callback {function} the optional completion callback
     */
    self.post = function (endpoint, data, callback = undefined) {
        return self.ajaxEndpoint('POST', endpoint, data, callback);
    };

    /**
     * Replace an API resource
     * @param endpoint {string}   the API path
     * @param data     {object}   the request body
     * @param callback {function} the optional completion callback
     */
    self.put = function (endpoint, data, callback = undefined) {
        return self.ajaxEndpoint('PUT', endpoint, data, callback);
    };

    /**
     * Delete an API resource
     * @param endpoint {string}   the API path
     * @param callback {function} the optional completion callback
     */
    self.delete = function (endpoint, callback = undefined) {
        return self.ajaxEndpoint('DELETE', endpoint, undefined, callback);
    };
    return self;
})();

// Keep the public browser API available to existing integrations
window.fs42Api = app.utils.routing;
