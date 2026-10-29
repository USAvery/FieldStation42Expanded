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
const context={window,app:{},encodeURIComponent,URL,URLSearchParams};
vm.runInNewContext(__SOURCE__,context);
const api={urlFor:context.urlFor,get:context.apiGet};
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
assert(!context.renderCatalogTable([catalog]).includes('<img'));
assert(!context.renderSummaryTable([{network_name:bad,catalog_summary:{entry_count:bad}}]).includes('<img'));
assert(!context.renderScheduleTable([block]).includes('<img'));
app.web_interface.catalog.displaySearchResults({results:[{network_name:bad,catalog_entries:[catalog]}]},bad);
assert(!output.innerHTML.includes('<img'));assert(output.innerHTML.includes('&lt;img'));
app.web_interface.schedule.displaySearchResults({results:[{network_name:bad,schedule_blocks:[block]}]},bad);
assert(!output.innerHTML.includes('<img'));assert(output.innerHTML.includes('&lt;img'));
app.web_interface.catalog.displaySearchResults({results:[]},bad);
assert(output.textContent.includes(bad));
"""
    result = subprocess.run([node, '-'], input=script, capture_output=True, encoding='utf8', timeout=20)
    assert result.returncode == 0, result.stderr


def test_reference_routing_helpers_callbacks_forms_and_lazy_routes(app):
    """
    Exercise reference-style helper signatures alongside the JSON API adapters
    """
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is required for browser utility checks')
    source = Path(_constants.STATIC_DIR, 'utils', 'routing.js').read_text(encoding='utf8')
    script = r"""
const vm=require('vm'),assert=require('assert');
const requests=[],navigations=[];
const config={root:'/station',paths:{'/text':'/station/text'},endpoints:{
    'api.example.item':'/station/items/{id}',
    'api.example.text':'/station/text',
    'widgets.example.static':'/station/static/example/{path}'
}};
class FormData {constructor(form){this.form=form}}
class DOMParser {parseFromString(text){return {title:text.match(/<title>(.*?)<\/title>/)[1]}}}
const form={id:'main-form'};
const window={$ROOT_PATH:'/station',location:{href:'http://localhost:18442/station/',
    origin:'http://localhost:18442',assign:url=>navigations.push(url)},fetch:async(url,options={})=>{
    requests.push({url,options});
    if(url==='/station/web/routes') return {ok:true,json:async()=>config};
    if(url==='/station/fail') return {ok:false,status:422,json:async()=>({detail:'Example validation failure'})};
    if(url==='/station/empty') return {ok:true,status:204};
    return {ok:true,status:200,text:async()=>'<title>Example</title>',json:async()=>({success:true})};
}};
const context={window,console,URL,URLSearchParams,FormData,DOMParser,
    document:{getElementById:id=>id==='main-form'?form:null}};
vm.runInNewContext(__SOURCE__,context);
(async()=>{
    let textCallback;
    const text=await context.ajaxEndpoint('api.example.text',{},value=>{textCallback=value});
    assert.equal(textCallback,text);
    assert.equal(requests.filter(r=>r.url==='/station/web/routes').length,1);
    assert.equal(context.urlFor('api.example.item',{id:'A & B',query:'one & two'}),
        '/station/items/A%20%26%20B?query=one+%26+two');
    assert.equal(context.urlFor('widgets.example.static',{},'images/a b.png'),
        '/station/static/example/images/a%20b.png');
    assert.equal(context.urlFor('/text?existing=yes#section',{extra:'x y'}),
        '/station/text?existing=yes&extra=x+y#section');
    assert.equal(context.convertArgsToStr({tag:['one','two'],empty:null}), '?tag=one&tag=two');
    const split=context.splitUrl('/text?tag=one&tag=two#section');
    assert.equal(split[0],'/text');assert.equal(JSON.stringify(split[1]),JSON.stringify({tag:['one','two']}));
    assert(context.isInternal('/station/text'));assert(!context.isInternal('https://example.com/'));
    let jsonCallback;
    await context.ajaxPost('/form',{value:'example'},value=>{jsonCallback=value},'json');
    assert(jsonCallback.success);assert.equal(requests.at(-1).options.body,'{"value":"example"}');
    await context.ajaxPost('/form',{},undefined,'json');
    assert.equal(requests.at(-1).options.body,'{}');
    await context.ajaxPost('/form',value=>{jsonCallback=value},'json');
    assert(requests.at(-1).options.body instanceof FormData);
    assert.equal(requests.at(-1).options.headers,undefined);
    assert.equal(await context.ajaxPost('/empty',{},undefined,'json'),null);
    await assert.rejects(context.fetchURL('/fail'),error=>error.status===422&&error.detail==='Example validation failure');
    assert.throws(()=>context.urlFor('api.example.missing'),/Endpoint not found/);
    assert.equal(await context.getPageTitle('/text'),'Example');
    let prevented=false;context.redirect('/text',{preventDefault:()=>{prevented=true}});
    assert(prevented);assert.equal(navigations.at(-1),'/station/text');
    assert((await context.apiPut('api.example.text',{})).success);
})().catch(error=>{console.error(error);process.exit(1)});
"""
    script = script.replace('__SOURCE__', json.dumps(source))
    result = subprocess.run([node, '-'], input=script, capture_output=True, encoding='utf8', timeout=20)
    assert result.returncode == 0, result.stderr


def test_blueprint_methods_are_available_without_starting_the_pages(app):
    """
    Load blueprint behavior without requiring page elements or starting requests and timers
    """
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is required for browser utility checks')
    directory = Path(_constants.WEB_DIR, 'blueprints')
    sources = {str(path.relative_to(directory)): path.read_text(encoding='utf8')
               for path in directory.rglob('*.js')}
    script = r"""
const vm=require('vm'),assert=require('assert');
for(const [name,source] of Object.entries(__SOURCES__)) {
    const app={};
    const unexpected=()=>{throw new Error(name+': started page behavior before setup')};
    const window={app,location:{search:''},addEventListener:unexpected};
    const context={window,app,URLSearchParams,WeakMap,localStorage:{getItem:()=>null},
        document:{getElementById:unexpected,querySelectorAll:unexpected,addEventListener:unexpected},
        setInterval:unexpected,setTimeout:unexpected,apiGet:unexpected,apiPost:unexpected,
        fetchURL:unexpected,escapeHtml:value=>String(value)};
    vm.runInNewContext(source,context,{filename:name});
    const parts=name.split(/[\\/]/);
    const module=app[parts[0]][parts[1]];
    assert.equal(typeof module.setup,'function',name);
    if(parts[1]==='on_demand') assert.equal(typeof module.renderView,'function');
    if(parts[1]==='customguide') assert.equal(typeof module.buildGrid,'function');
    if(parts[1]==='ppv') assert.equal(typeof module.randomOtherIndex,'function');
    if(parts[1]==='bump') assert.equal(typeof window.StationBump,'function');
}
"""
    script = script.replace('__SOURCES__', json.dumps(sources))
    result = subprocess.run([node, '-'], input=script, capture_output=True, encoding='utf8', timeout=20)
    assert result.returncode == 0, result.stderr


def test_widget_instances_keep_controls_and_handlers_independent(app):
    """
    Use widget behavior outside setup without sharing one instance's controls with another
    """
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is required for browser utility checks')
    sources = [(Path(_constants.WEB_DIR) / 'blueprints/widgets' / name / 'static' / (name + '.js')).read_text()
               for name in ('selector', 'search', 'log_display')]
    script = r"""
const vm=require('vm'),assert=require('assert');const elements=new Map();
function element(id) {
    if(!elements.has(id)) elements.set(id,{style:{display:'none'},children:[],value:'',
        replaceChildren(){this.children=[]},appendChild(child){this.children.push(child)},
        addEventListener(name,handler){this[name]=handler}});
    return elements.get(id);
}
const app={},window={app};const context={app,window,document:{getElementById:element,createElement:()=>({})}};
for(const source of __SOURCES__) vm.runInNewContext(source,context);
const one=app.widgets.selector.setup({attributes:{id:'one'}});
const two=app.widgets.selector.setup({attributes:{id:'two'}});
one.setOptions([{value:'one',label:'Example'}],'one');
assert.equal(one.getValue(),'one');assert.equal(element('two').children.length,0);
let calls=0;
const first=app.widgets.search.setup({id:'first',loading:'Loading'});
const second=app.widgets.search.setup({id:'second',loading:'Waiting'});
first.bind(()=>calls++,()=>{});second.bind(()=>calls+=10,()=>{});
element('first-input').onkeydown({key:'Enter',preventDefault:()=>{}});
assert.equal(calls,1);first.busy(true);assert.equal(element('first-btn').disabled,true);
assert.equal(element('second-btn').disabled,undefined);
const log=app.widgets.log_display.setup({prefix:'first'});
app.widgets.log_display.setup({prefix:'second'});
log.show('Message');assert.equal(element('first-log').textContent,'Message');
assert.equal(element('second-log').textContent,undefined);
element('first-log-dismiss').onclick();assert.equal(element('first-log-frame').style.display,'none');
"""
    script = script.replace('__SOURCES__', json.dumps(sources))
    result = subprocess.run([node, '-'], input=script, capture_output=True, encoding='utf8', timeout=20)
    assert result.returncode == 0, result.stderr


def test_menu_pages_render_the_shared_clock_widget(app):
    """
    Preserve menu clock IDs and load the shared implementation once per page
    """
    with TestClient(app) as client:
        for url, control in [('/static/customguide/customguide.html', 'clock'), ('/on-demand', 'od-clock')]:
            html = client.get(url).text
            assert '<time id="{}"'.format(control) in html
            assert html.count('app.menu_widgets.menu_clock.setup(') == 1
            assert '<div class="menu-clock-line">' in html
            assert 'data-variant' not in html
            assert html.count('/static/menu_widgets/menu_clock/menu_clock.js') == 1
            assert html.count('/static/menu_widgets/menu_clock/menu_clock.css') == 1
        assert client.get('/static/menu_widgets/menu_clock/menu_clock.js').status_code == 200
        assert client.get('/static/menu_widgets/menu_clock/menu_clock.css').status_code == 200


def test_menu_clock_ticks_replaces_instances_and_releases_timers(app):
    """
    Update independent clocks each second without leaking replacement or detached timers
    """
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is required for browser utility checks')
    source = Path(_constants.WEB_DIR, 'static/utils/datetime.js').read_text() + '\n' + Path(
        _constants.WEB_DIR, 'blueprints/menu_widgets/menu_clock/static/menu_clock.js').read_text()
    script = r"""
const vm=require('vm'),assert=require('assert');
const elements={one:{isConnected:true},two:{isConnected:true}};
const timers=new Map(),listeners=new Map();let id=0,now=Date.parse('2026-10-28T13:45:00Z');
class ClockDate extends Date {constructor(){super(now)}}
const app={},window={app,addEventListener:(name,fn)=>listeners.set(name,fn),
    removeEventListener:(name,fn)=>{if(listeners.get(name)===fn)listeners.delete(name)}};
const context={app,window,Date:ClockDate,Intl,document:{getElementById:name=>elements[name]},
    setInterval:(fn,ms)=>{assert.equal(ms,1000);timers.set(++id,fn);return id},
    clearInterval:id=>timers.delete(id)};
vm.runInNewContext(__SOURCE__,context);
const config={attributes:{id:'one'},locale:'en-US',compact:true,
    options:{hour:'numeric',minute:'2-digit',hour12:true,timeZone:'UTC'}};
const widget=app.menu_widgets.menu_clock;
const first=widget.setup(config);
assert.equal(elements.one.textContent,'1:45pm');assert.equal(timers.size,1);
const previous=elements.one.dateTime;now+=1000;timers.get(first.timer)();
assert.notEqual(elements.one.dateTime,previous);
const second=widget.setup({...config,attributes:{id:'two'},compact:false});
assert.equal(elements.two.textContent,'1:45 PM');assert.equal(timers.size,2);
widget.setup(config);assert.equal(first.timer,null);assert.equal(timers.size,2);
elements.two.isConnected=false;timers.get(second.timer)();assert.equal(second.timer,null);
assert.equal(timers.size,1);listeners.get('beforeunload')();assert.equal(timers.size,0);
assert.equal(Object.keys(widget.instances).length,0);
"""
    script = script.replace('__SOURCE__', json.dumps(source))
    result = subprocess.run([node, '-'], input=script, capture_output=True, encoding='utf8', timeout=20)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('video,title', [(False, None), (True, 'TV Listings'), (False, '<img src=x onerror=alert(1)>')])
def test_menu_top_panel_options_and_caller_content(app, video, title):
    """
    Render optional preview and title while keeping caller content composable and escaped
    """
    @app.get('/panel-example', include_in_schema=False)
    def example(request: Request):
        template = app.state.templates.env.from_string(
            "{% call include_widget('menu_top_panel', config) %}"
            '<strong id="custom-details">{{ details }}</strong>{% endcall %}')
        return HTMLResponse(template.render(request=request, config={'video_panel': video, 'title': title},
                                            details='<script>unsafe()</script>'))

    with TestClient(app) as client:
        html = client.get('/panel-example').text
        assert ('id="video-panel"' in html) is video
        assert ('class="menu-top-panel-title"' in html) is (title is not None)
        assert '<strong id="custom-details">&lt;script&gt;unsafe()&lt;/script&gt;</strong>' in html
        assert '<img src=x' not in html
        assert 'app.menu_widgets.menu_clock.setup(' in html
        assert 'id="selected-program-title"' not in html


def test_menu_top_panel_default_options_and_guide_integration(app):
    """
    Omit the preview and title by default, and preserve the guide's native-preview hook and details
    """
    @app.get('/default-panel', include_in_schema=False)
    def default_panel(request: Request):
        template = app.state.templates.env.from_string("{{ include_widget('menu_top_panel') }}")
        return HTMLResponse(template.render(request=request))

    with TestClient(app) as client:
        html = client.get('/default-panel').text
        assert 'id="video-panel"' not in html
        assert 'class="menu-top-panel-title"' not in html
        guide = client.get('/static/customguide/customguide.html').text
        for control in ('top-panel', 'video-panel', 'selected-program-title', 'selected-channel-label',
                        'selected-program-time', 'selected-program-icons', 'selected-program-description', 'clock'):
            assert 'id="{}"'.format(control) in guide
        assert 'menu-top-panel-details' in guide
        assert 'TV Listings' in guide
        assert guide.count('/static/menu_widgets/menu_top_panel/menu_top_panel.css') == 1
        for file in ('menu_top_panel.css', 'images/comcast_logo.png', 'images/tv_guide_logo.png'):
            assert client.get('/static/menu_widgets/menu_top_panel/' + file).status_code == 200


def test_menu_bottom_panel_replaces_guide_promo_and_loads_its_styles(app):
    """
    Keep the guide layout while loading the renamed bottom panel through widget assets
    """
    with TestClient(app) as client:
        html = client.get('/static/customguide/customguide.html').text
        assert 'id="menu-bottom-panel"' in html
        assert 'guide-promo' not in html
        assert html.count('/static/menu_widgets/menu_bottom_panel/menu_bottom_panel.css') == 1
        response = client.get('/static/menu_widgets/menu_bottom_panel/menu_bottom_panel.css')
        assert response.status_code == 200
        assert '.menu-bottom-panel {' in response.text


def test_menu_bottom_panel_accepts_caller_html_and_preserves_escaping(app):
    """
    Supply page-owned HTML without making ordinary template values trusted HTML
    """
    @app.get('/bottom-example', include_in_schema=False)
    def example(request: Request):
        template = app.state.templates.env.from_string(
            "{% call include_widget('menu_bottom_panel') %}"
            '<strong id="bottom-message">{{ message }}</strong>{% endcall %}')
        return HTMLResponse(template.render(request=request, message='<script>unsafe()</script>'))

    with TestClient(app) as client:
        html = client.get('/bottom-example').text
        assert '<strong id="bottom-message">&lt;script&gt;unsafe()&lt;/script&gt;</strong>' in html
        assert 'aria-hidden="true"' not in html
        assert 'id="menu-bottom-panel"' in html


def test_menu_widgets_have_separate_discovery_settings_and_page_assets(app):
    """
    Keep Pi components out of console widget discovery and console page asset lists
    """
    assert set(widget.get_widgets(groups=('widgets',))) == {'selector', 'search', 'log_display'}
    assert set(widget.get_widgets(groups=('menu_widgets',))) == {'menu_clock', 'menu_top_panel', 'menu_bottom_panel', 'on_demand_controls'}
    assert 'menu_clock' in app.state.web_settings['menu_widgets']
    assert 'menu_clock' not in app.state.web_settings['widgets']
    with TestClient(app) as client:
        console = client.get('/static/catalog.html').text
        assert 'src="/static/menu_widgets/' not in console
        assert 'href="/static/menu_widgets/' not in console
        assert '/static/widgets/selector/selector.js' in console
        menu = client.get('/static/customguide/customguide.html').text
        assert 'src="/static/widgets/' not in menu
        assert 'href="/static/widgets/' not in menu
        assert '/static/menu_widgets/menu_clock/menu_clock.js' in menu
        assert '/static/menu_widgets/menu_top_panel/menu_top_panel.css' in menu


def test_shared_datetime_and_css_helpers():
    """Preserve local timestamps, compact display, interval boundaries, and element CSS values."""
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is required for browser utility checks')
    source = '\n'.join(Path(_constants.WEB_DIR, 'static/utils', name).read_text()
                       for name in ('datetime.js', 'css.js'))
    script = r"""
const assert=require('assert');
const root={},child={};const document={documentElement:root};
function getComputedStyle(element){return {getPropertyValue:name=>element===root?'  blue  ':'  red  '}}
__SOURCE__
const date=new Date(2026,0,2,13,5,9);
assert.equal(formatLocalDateTime(date),'2026-01-02T13:05:09');
assert.equal(formatTime(date),'1:05pm');
assert.equal(formatTime(date,{short_suffix:true}),'1:05p');
assert.equal(formatTime(date,{compact:false}),'1:05 PM');
assert.equal(formatTimeRange(new Date(2026,0,2,13),new Date(2026,0,2,14,30)),'1-2:30p');
assert.equal(formatTimeRange(date,new Date(2026,0,2,14),
    {hide_zero_minutes:false,short_suffix:false,start_suffix:true}),'1:05pm-2:00pm');
const slots=computeTimeSlots(new Date(2026,0,2,23,50),{interval:15,count:2,offset:1});
assert.equal(formatLocalDateTime(slots[0].start),'2026-01-03T00:00:00');
assert.equal(formatLocalDateTime(slots[1].end),'2026-01-03T00:30:00');
assert.equal(date.getHours(),13);
assert.equal(computeTimeSlots(date,{count:0}).length,0);
assert.throws(()=>computeTimeSlots(date,{interval:0}),RangeError);
assert.equal(getCSSVar('--color'),'blue');assert.equal(getCSSVar('--color',child),'red');
"""
    result = subprocess.run([node, '-'], input=script.replace('__SOURCE__', source),
                            capture_output=True, encoding='utf8', timeout=20)
    assert result.returncode == 0, result.stderr


def test_customguide_starts_and_builds_its_grid():
    """Exercise guide startup so missing method references cannot leave an empty guide."""
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is required for browser utility checks')
    source = Path(_constants.WEB_DIR, 'static/utils/datetime.js').read_text() + '\n' + Path(_constants.WEB_DIR, 'blueprints/menu/customguide/static/customguide.js').read_text()
    script = r"""
const vm=require('vm'),assert=require('assert');
const app={},events=[],strip={},listings={appendChild:node=>assert.equal(node,strip)};
const context={app,window:{app,location:{search:''},addEventListener:name=>events.push(name)},
    URLSearchParams,document:{getElementById:id=>{assert.equal(id,'grid-listings');return listings}}};
vm.runInNewContext(__SOURCE__,context);
const guide=app.menu.customguide;let headers=0,initialized=false;
guide.fetchStations=async()=>{};
guide.updateGridHeader=slots=>{assert.equal(slots.length,4);headers++};
guide.fetchAllSchedules=async slots=>{assert.equal(slots.length,4);return {}};
guide.buildGridStrip=slots=>{assert.equal(slots.length,4);return strip};
guide.initGridInteraction=()=>{initialized=true};
const selectCurrentChannel=guide.selectCurrentChannel;
guide.selectCurrentChannel=async()=>{};
(async()=>{await guide.setup();assert(initialized);assert.equal(headers,1);
    assert(events.includes('fs42-guide-show'));
    const rows=[1,7,12].map(channel=>({dataset:{channelNumber:String(channel)}}));
    guide.getInteractiveRows=()=>rows;
    guide.getProgramsForRow=()=>[{classList:{contains:()=>true}}];
    let chosen;
    guide.applyInteractiveSelection=()=>{chosen=rows.indexOf(lastRow)};
    let lastRow;
    guide.getProgramsForRow=row=>{lastRow=row;return [{classList:{contains:()=>true}}]};
    context.apiGet=async endpoint=>{assert.equal(endpoint,'api.player.get_player_status');return {channel_number:7}};
    await selectCurrentChannel();assert.equal(chosen,1);
    context.apiGet=async()=>({channel_number:99});
    await selectCurrentChannel();assert.equal(chosen,0);
})().catch(e=>{console.error(e);process.exitCode=1});
"""
    result = subprocess.run([node, '-'], input=script.replace('__SOURCE__', json.dumps(source)),
                            capture_output=True, encoding='utf8', timeout=20)
    assert result.returncode == 0, result.stderr


def test_menu_top_panel_serves_the_tv_guide_image(app):
    """Keep the real TV Guide logo in the shared header on both Pi pages."""
    logo = '/static/menu_widgets/menu_top_panel/images/tv_guide_logo.png'
    with TestClient(app) as client:
        for page in ('/static/customguide/customguide.html', '/on-demand'):
            assert 'src="{}" alt="TV Guide"'.format(logo) in client.get(page).text
        response = client.get(logo)
        assert response.status_code == 200
        assert response.headers['content-type'] == 'image/png'


def test_web_remote_back_sends_menu_key_without_leaving_remote(app):
    """Expose Back on the remote and send Escape through its existing menu-key transport."""
    with TestClient(app) as client:
        html = client.get('/remote').text
        assert 'data-key="back" aria-label="Back"' in html
        assert html.index('id="nav-pad"') < html.index('data-key="back"') < html.index('data-key="nav_left"')
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is required for browser utility checks')
    source = Path(_constants.WEB_DIR, 'blueprints/web_interface/remote/static/remote.js').read_text(encoding='utf8')
    script = r"""
const vm=require('vm'),assert=require('assert');
const app={},location={href:'/remote'};
vm.runInNewContext(__SOURCE__,{app,window:{app,location},setTimeout:()=>{}});
const remote=app.web_interface.remote;let sent=[];
remote.sendPpvKey=async(...args)=>sent.push(args);
(async()=>{await remote.handleRemoteCommand('back');
    assert.deepEqual(sent,[['Escape','BACK']]);assert.equal(location.href,'/remote');
})().catch(e=>{console.error(e);process.exitCode=1});
"""
    result = subprocess.run([node, '-'], input=script.replace('__SOURCE__', json.dumps(source)),
                            capture_output=True, encoding='utf8', timeout=20)
    assert result.returncode == 0, result.stderr


def test_on_demand_back_closes_at_the_root():
    """Back exits from the root, navigates submenus, and keeps PageUp separate."""
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is required for browser utility checks')
    source = Path(_constants.WEB_DIR, 'blueprints/menu/on_demand/static/on_demand.js').read_text()
    script = r"""
const vm=require('vm'),assert=require('assert');
const app={},location={href:'/on-demand'},closes=[];
vm.runInNewContext(__SOURCE__,{
    app,window:{app,location},apiPost:async name=>closes.push(name),
    document:{body:{classList:{contains:()=>false}},querySelectorAll:()=>[]}
});
const menu=app.menu.on_demand;let renders=0;
menu.renderView=()=>renders++;
menu.goBack();assert.equal(renders,0);assert.deepEqual(closes,['api.player.close_menu']);
menu.openView({type:'titles',title:'TV Shows'});assert.equal(renders,1);
menu.goBack();assert.equal(renders,2);assert.equal(closes.length,1);
for(const key of ['Escape','Backspace','PageUp']) {
    menu.onKeydown({key,preventDefault(){}});assert.equal(location.href,'/on-demand');
}
assert.deepEqual(closes,['api.player.close_menu','api.player.close_menu','api.player.close_menu']);
"""
    result = subprocess.run([node, '-'], input=script.replace('__SOURCE__', json.dumps(source)),
                            capture_output=True, encoding='utf8', timeout=20)
    assert result.returncode == 0, result.stderr


def test_on_demand_uses_both_shared_menu_panels(app):
    """
    Preserve browsing controls and preview hooks inside the reusable panel layouts
    """
    with TestClient(app) as client:
        html = client.get('/on-demand').text
        assert 'menu-top-panel--video' in html
        assert 'class="menu-top-panel-details"' in html
        assert 'id="menu-bottom-panel"' in html
        for control in ('video-panel', 'od-clock', 'od-heading', 'od-selection', 'od-options',
                        'od-search', 'od-query', 'od-details', 'od-title', 'od-navigation'):
            assert html.count('id="{}"'.format(control)) == 1
        assert 'id="od-top"' not in html
        assert 'id="od-footer"' not in html
        assert html.index('id="menu-bottom-panel"') < html.index('id="od-navigation"')
        assert 'menu_buttom_panel' not in html
        assert '/static/menu_widgets/menu_bottom_panel/menu_bottom_panel.css' in html
        assert client.get('/static/menu_widgets/menu_bottom_panel/menu_bottom_panel.css').status_code == 200

def test_custom_guide_back_closes_the_overlay():
    """Back from the guide closes the overlay without changing the station."""
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is required for browser utility checks')
    source = Path(_constants.WEB_DIR, 'blueprints/menu/customguide/static/customguide.js').read_text(encoding='utf8')
    script = r"""
const vm=require('vm'),assert=require('assert');
const app={},closes=[],location={search:''};
vm.runInNewContext(__SOURCE__,{
    app,window:{app,location},URLSearchParams,apiPost:async name=>closes.push(name)
});
(async()=>{
    const guide=app.menu.customguide;
    for(const key of ['Escape','Backspace']) {
        let prevented=false,stopped=false;
        await guide.handleInteractiveKeydown({
            key,preventDefault(){prevented=true},stopPropagation(){stopped=true}
        });
        assert(prevented && stopped);
    }
    assert.deepEqual(closes,['api.player.close_menu','api.player.close_menu']);
})().catch(e=>{console.error(e);process.exitCode=1});
"""
    result = subprocess.run([node, '-'], input=script.replace('__SOURCE__', json.dumps(source)),
                            capture_output=True, encoding='utf8', timeout=20)
    assert result.returncode == 0, result.stderr
