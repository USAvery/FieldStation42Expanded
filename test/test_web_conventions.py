#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Check configurable registration, browser routes, widgets, and shared error responses.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from fastapi.responses import HTMLResponse

from fs42.web.app import create_app
from fs42.web.remote_app import create_app as create_remote
from fs42.web.core import settings
from fs42.web.core import widget
from fs42.web.core import _constants


@pytest.fixture
def app(tmp_path, monkeypatch):
    """
    Isolate generated files and web settings from local station configuration
    """
    monkeypatch.delenv('FS42_WEB_SETTINGS', raising=False)
    monkeypatch.setattr(_constants, 'GUIDE_VIDEO_DIR', str(tmp_path / 'guide_videos'))
    return create_app(server_conf={})


def test_settings_merge_preserves_nested_defaults_and_inputs():
    """
    Merge nested overrides without sharing mutable configuration between instances
    """
    base = {'widget': {'attributes': {'id': 'one', 'class': 'input'}, 'options': []}}
    updated = settings.merge(base, {'widget': {'attributes': {'id': 'two'}}})
    assert updated['widget']['attributes'] == {'id': 'two', 'class': 'input'}
    updated['widget']['options'].append('changed')
    assert base['widget']['options'] == []
    assert base['widget']['attributes']['id'] == 'one'


def test_settings_file_and_server_overrides_are_application_local(app, tmp_path, monkeypatch):
    """
    Apply file settings before per-application overrides without altering another app
    """
    override = tmp_path / 'web.json'
    override.write_text(json.dumps({'widgets': {'selector': {'config': {'label': 'Choose network'}}}}))
    monkeypatch.setenv('FS42_WEB_SETTINGS', str(override))
    second = create_app(server_conf={'web': {'widgets': {'selector': {'config': {'attributes': {'class': 'wide'}}}}}})
    config = second.state.web_settings['widgets']['selector']['config']
    assert config['label'] == 'Choose network'
    assert config['attributes'] == {'id': 'station-select', 'class': 'wide'}
    assert app.state.web_settings['widgets']['selector']['config']['label'] == 'Select Station:'


@pytest.mark.parametrize('disabled', ['catalog', 'web_interface.catalog'])
def test_disabled_page_has_no_routes_assets_or_navigation(app, disabled):
    """
    Disable a package consistently across registration, navigation, and route exports
    """
    current = create_app(server_conf={'web': {'disabled_blueprints': [disabled]}})
    with TestClient(current) as client:
        assert client.get('/static/catalog.html').status_code == 404
        assert client.get('/static/web_interface/catalog/catalog.js').status_code == 404
        assert '>Catalog</a>' not in client.get('/').text
        assert 'catalog.index' not in client.get('/web/routes').json()['endpoints']


def test_disabled_home_does_not_break_other_console_pages(app):
    """
    Keep the remaining templates usable when a linked blueprint is disabled
    """
    with TestClient(create_app(server_conf={'web': {'disabled_blueprints': ['web_interface.index']}})) as client:
        response = client.get('/static/about.html')
        assert response.status_code == 200
        assert '>Home</a>' not in response.text


def test_route_map_tracks_prefixes_root_path_and_assets(app):
    """
    Give server-rendered links and browser requests the same mounted URLs
    """
    config = {'root_path': '/station', 'url_prefixes': {'web_interface.catalog': '/console', 'api.summary': '/service'}}
    with TestClient(create_app(server_conf={'web': config})) as client:
        html = client.get('/station/console/static/catalog.html').text
        assert 'src="/station/console/static/web_interface/catalog/catalog.js"' in html
        assert 'href="/station/console/static/catalog.html"' in html
        assert client.get('/station/console/static/web_interface/catalog/catalog.js').status_code == 200
        routes = client.get('/station/web/routes').json()
        assert routes['endpoints']['api.summary.get_summary'] == '/station/service/summary/'
        assert routes['paths']['/summary'] == '/station/service/summary/'
        assert routes['paths']['/static/catalog.html'] == '/station/console/static/catalog.html'
        assert '/station/station/' not in html


def test_standalone_remote_uses_the_same_configurable_registration(app):
    """
    Respect API prefixes in the remote without registering main-console pages
    """
    current = create_remote({'web': {'url_prefixes': {'api.remote_control': '/handset'}}})
    with TestClient(current) as client:
        assert client.get('/').status_code == 200
        config = client.get('/web/routes').json()
        assert config['endpoints']['api.remote_control.handle_command'] == '/handset/api/command'
        assert client.get('/static/utils/routing.js').status_code == 200
        assert client.get('/static/catalog.html').status_code == 404


def test_widget_defaults_and_instances_escape_attributes_and_script_data(app):
    """
    Render independent widget instances with safe HTML and JSON configuration
    """
    dangerous = '</script><img src=x onerror=alert(1)>'

    @app.get('/widget-example', include_in_schema=False)
    def example(request: Request):
        source = "{{ include_widget('selector', first) }}{{ include_widget('selector', second) }}"
        template = app.state.templates.env.from_string(source)
        return HTMLResponse(template.render(request=request,
                            first={'label': dangerous, 'attributes': {'id': 'one', 'title': dangerous}},
                            second={'attributes': {'id': 'two'}, 'options': [{'value': dangerous, 'label': dangerous}]}))

    with TestClient(app) as client:
        html = client.get('/widget-example').text
        assert '<img src=x' not in html
        assert '&lt;/script&gt;' in html
        assert 'id="one"' in html and 'id="two"' in html
        assert 'name="one"' in html and 'name="two"' in html
        assert html.count('app.widgets.selector.setup(') == 2
    assert app.state.web_settings['widgets']['selector']['config']['attributes']['id'] == 'station-select'


@pytest.mark.parametrize('name', ['onmouseover', 'x" onclick="run()', 'bad name'])
def test_widget_attribute_names_cannot_introduce_handlers(name):
    """
    Reject attribute keys that could bypass escaped attribute values
    """
    with pytest.raises(ValueError):
        widget.render_attributes({name: 'value'})


@pytest.mark.parametrize('debug', [False, True])
def test_unexpected_errors_log_and_render_without_leaking_normal_tracebacks(app, caplog, debug):
    """
    Keep traceback details in server logs and explicitly enabled debug pages
    """
    app.state.web_settings['debug'] = debug

    @app.get('/broken-page', include_in_schema=False)
    def broken():
        raise RuntimeError('private failure detail')

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get('/broken-page', headers={'accept': 'text/html'})
        assert response.status_code == 500
        assert ('private failure detail' in response.text) is debug
        assert 'private failure detail' in caplog.text
        response = client.get('/broken-page', headers={'accept': 'application/json'})
        assert response.json() == {'detail': 'An unexpected error occurred.'}


def test_http_and_validation_errors_keep_json_contracts(app):
    """
    Render missing pages as HTML and retain structured API validation failures
    """
    with TestClient(app) as client:
        response = client.get('/missing-page', headers={'accept': 'text/html'})
        assert response.status_code == 404
        assert '<h1>404' in response.text
        response = client.post('/stations', json={}, headers={'accept': 'text/html'})
        assert response.status_code == 422
        assert isinstance(response.json()['detail'], list)


def test_browser_routes_use_registered_paths_and_current_origin(app):
    """
    Resolve named parameters, legacy paths, and query strings without a fixed port
    """
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is required for browser utility checks')
    source = Path(_constants.STATIC_DIR, 'utils', 'routing.js').read_text(encoding='utf8')
    config = {'root': '/station', 'paths': {'/summary': '/station/service/summary/',
              '/catalogs/{network_name}': '/station/library/catalogs/{network_name}',
              '/static/{path}': '/station/static/{path}'},
              'endpoints': {'api.catalogs.get_catalog': '/station/library/catalogs/{network_name}'}}
    script = r"""
const assert=require('assert'),vm=require('vm');
const calls=[];
const window={fs42Routes:__CONFIG__,fetch:async(url,options)=>{
    calls.push(url);
    return {ok:true,status:200,json:async()=>({ok:true})};
}};
const context={window,app:{},encodeURIComponent};
vm.runInNewContext(__SOURCE__,context);
const api=window.fs42Api;
assert.equal(api.urlFor('api.catalogs.get_catalog',{network_name:'A & B'}),'/station/library/catalogs/A%20%26%20B');
assert.equal(api.urlFor('/catalogs/Example?q=a%26b'),'/station/library/catalogs/Example?q=a%26b');
assert.equal(api.urlFor('/static/themes/retro.css'),'/station/static/themes/retro.css');
assert.equal(api.urlFor('/station/static/themes/retro.css'),'/station/static/themes/retro.css');
api.get('summary').then(()=>{
    assert.equal(calls[0],'/station/service/summary/');
}).catch(error=>{console.error(error);process.exit(1)});
"""
    script = script.replace('__CONFIG__', json.dumps(config)).replace('__SOURCE__', json.dumps(source))
    result = subprocess.run([node, '-'], input=script, capture_output=True, encoding='utf8', timeout=20)
    assert result.returncode == 0, result.stderr


def test_main_configuration_passes_web_overrides_to_the_application(app):
    """
    Retain the web section while loading ordinary station configuration
    """
    from types import SimpleNamespace
    from fs42.core.station_manager import StationManager
    configured = {'url_prefixes': {'api.summary': '/service'}}
    manager = SimpleNamespace(server_conf={},
                              station_io=SimpleNamespace(load_main_config=lambda: {'web': configured}),
                              _validate_custom_holiday_names=lambda: None)
    StationManager.load_main_config(manager)
    assert settings.load(manager.server_conf)['url_prefixes'] == configured['url_prefixes']


def test_table_and_search_renderers_escape_display_data(app):
    """
    Keep query strings, catalog metadata, and schedule text out of HTML markup
    """
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is required for browser utility checks')
    web = Path(_constants.WEB_DIR)
    sources = [(web / 'static/utils/general.js').read_text(encoding='utf8')]
    for name in ('catalog', 'schedule', 'stations'):
        sources.append((web / 'blueprints/web_interface' / name / 'static' / (name + '.js')).read_text(encoding='utf8'))
    script = r"""
const vm=require('vm'),assert=require('assert');
const output={innerHTML:'',textContent:''};
const app={};const window={app,addEventListener:()=>{}};
const context={window,app,document:{getElementById:()=>output}};
"""
    for source in sources:
        script += 'vm.runInNewContext(' + json.dumps(source) + ',context);\n'
    script += r"""
const bad='<img src=x onerror=alert(1)>';
const catalog={title:bad,path:'" title="'+bad,duration:1,count:bad,hints:[bad]};
const block={title:bad,station_name:bad,start_time:'2026-10-28T00:00:00',end_time:'2026-10-28T01:00:00'};
assert(app.web_interface.stations.escapeHtml('\" data-x=\"').includes('&quot;'));
assert(!app.utils.general.renderCatalogTable([catalog]).includes('<img'));
assert(!app.utils.general.renderSummaryTable([{network_name:bad,catalog_summary:{entry_count:bad}}]).includes('<img'));
assert(!app.utils.general.renderScheduleTable([block]).includes('<img'));
app.web_interface.catalog.displaySearchResults({results:[{network_name:bad,catalog_entries:[catalog]}]},bad);
assert(!output.innerHTML.includes('<img'));assert(output.innerHTML.includes('&lt;img'));
app.web_interface.schedule.displaySearchResults({results:[{network_name:bad,schedule_blocks:[block]}]},bad);
assert(!output.innerHTML.includes('<img'));assert(output.innerHTML.includes('&lt;img'));
app.web_interface.catalog.displaySearchResults({results:[]},bad);
assert(output.textContent.includes(bad));
"""
    result = subprocess.run([node, '-'], input=script, capture_output=True, encoding='utf8', timeout=20)
    assert result.returncode == 0, result.stderr
