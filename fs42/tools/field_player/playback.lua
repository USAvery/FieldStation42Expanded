-- Select the video output after demuxing, before opening any decoder.
local mp = require('mp')
local options = require('mp.options')
local settings = {direct = false, pi4 = false}
local force_fallback = false

options.read_options(settings, 'fs42-playback')

mp.register_script_message('force-fallback', function(value)
    force_fallback = value == 'yes'
end)

mp.add_hook('on_preloaded', 10, function()
    local codec = ''
    for _, track in ipairs(mp.get_property_native('track-list', {})) do
        if track.type == 'video' and not track.albumart and not track.image then
            codec = track.codec or ''
            break
        end
    end

    local filters = mp.get_property_native('vf', {})
    -- MPV 0.35 on Pi 4 can keep decoding HEVC while its DMA-BUF surface
    -- stops updating. Copy-back retains the hardware decoder and presents
    -- through the native Wayland GPU path without replacing MPV.
    local legacy_pi4_hevc = settings.pi4 and codec == 'hevc'
        and mp.get_property('mpv-version', ''):match('^mpv 0%.35%.')
    local direct = settings.direct and not force_fallback and not legacy_pi4_hevc
        and (codec == 'h264' or codec == 'hevc') and #filters == 0
    local output = direct and 'dmabuf-wayland' or 'gpu'
    local decoder = direct and 'auto' or 'auto-copy'

    if mp.get_property('vo') ~= output then
        mp.set_property('vo', output)
    end
    mp.set_property('hwdec', decoder)
    mp.commandv('script-message', 'fs42-output', output, codec)
end)
