/*
This Source Code Form is subject to the Mozilla Public License, v. 2.0.
See https://mozilla.org/MPL/2.0/.
*/
window.app = window.app || {};
app.menu = app.menu || {};
app.menu.bump = (function () {
    let self = {};
    /**
     * Set up the bump page
     */
    self.setup = function () {
        class StationBump {
            /**
             * Constructor
             */
            constructor(config = {}) {
                this.container = document.getElementById('bumpContainer');
                this.backgroundLayer = document.getElementById('backgroundLayer');
                this.bgVideoPlayer = document.getElementById('bgVideoPlayer');
                this.contentArea = document.getElementById('contentArea');
                this.mainTitle = document.getElementById('mainTitle');
                this.subtitle = document.getElementById('subtitle');
                this.detailLine1 = document.getElementById('detailLine1');
                this.detailLine2 = document.getElementById('detailLine2');
                this.detailLine3 = document.getElementById('detailLine3');
                this.bgMusicPlayer = document.getElementById('bgMusicPlayer');
                this.countdownTimer = document.getElementById('countdownTimer');
                this.countdownDisplay = document.getElementById('countdownDisplay');
                this.videoLoopsRemaining = 1;
                this.textLoopTimers = [];
                this.config = {
                    title: 'FieldStation42',
                    subtitle: 'Big Time Watching Is Here!',
                    details: ['Transmitting 24/7', 'On FieldStation42', "It's up to you!"],
                    backgroundImage: null,
                    backgroundVideo: null,
                    backgroundVideoLoopCount: 1,
                    backgroundVideoAudio: true,
                    backgroundColor: '#000000',
                    bgColor: null,
                    fgColor: null,
                    theme: 'dark',
                    accentColor: 'white',
                    duration: 0,
                    nextUp: null,
                    variation: 'modern',
                    cssOverride: null,
                    bgMusic: null,
                    loopMusic: true,
                    countdown: false,
                    textPosition: null,
                    textDelay: 0,
                    textFadeIn: 0,
                    textFadeOut: 0,
                    textHideBeforeEnd: 0,
                    ...config
                };
                this.init();
            }
            /**
             * Init
             */
            async init() {
                await this.applyConfiguration();
                this.setupTextPresentation();
                this.setupAutoHide();
                this.setupCountdown();
            }
            /**
             * Apply Configuration
             */
            async applyConfiguration() {
                // Set content
                this.mainTitle.textContent = this.config.title;
                this.subtitle.textContent = this.config.subtitle;

                // Handle nextUp shows or regular details
                if (this.config.nextUp) {
                    await this.loadNextUpShows();
                }
                else {
                    // Set regular detail lines
                    const detail_elements = [this.detailLine1, this.detailLine2, this.detailLine3];
                    this.config.details.forEach(function (detail, index) {
                        if (detail_elements[index]) {
                            detail_elements[index].textContent = detail;
                            detail_elements[index].style.display = detail ? 'block' : 'none';
                        }
                    });
                }

                // Set background
                if (this.config.backgroundVideo) {
                    this.setupBackgroundVideo();
                }
                else if (this.config.backgroundImage) {
                    this.backgroundLayer.style.backgroundImage = 'url(' + this.config.backgroundImage + ')';
                    this.container.classList.add('custom-bg');
                }
                else if (this.config.bgColor) {
                    this.container.style.background = this.config.bgColor;
                }
                else {
                    this.container.style.background = this.config.backgroundColor;
                }

                // Apply variation styling
                this.applyVariation();

                // Load custom CSS override if provided
                if (this.config.cssOverride) {
                    this.loadCSSOverride();
                }

                // Set custom text colors (overrides variation defaults if provided)
                if (this.config.fgColor) {
                    this.mainTitle.style.color = this.config.fgColor;
                    this.subtitle.style.color = this.config.fgColor;
                    this.detailLine1.style.color = this.config.fgColor;
                    this.detailLine2.style.color = this.config.fgColor;
                    this.detailLine3.style.color = this.config.fgColor;
                }

                // Handle background music
                this.setupBackgroundMusic();
            }
            /**
             * Apply Variation
             */
            applyVariation() {
                // Remove any existing variation classes
                this.container.classList.remove(
                    'variation-modern',
                    'variation-retro',
                    'variation-corporate',
                    'variation-terminal'
                );

                // Add the selected variation class
                this.container.classList.add('variation-' + this.config.variation);

                // Set default colors based on variation (only if custom colors not provided)
                if (!this.config.bgColor && !this.config.backgroundImage && !this.config.backgroundVideo) {
                    const variation_defaults = this.getVariationDefaults();
                    if (variation_defaults.bgColor) {
                        this.container.style.background = variation_defaults.bgColor;
                    }
                }
            }
            /**
             * Get Variation Defaults
             */
            getVariationDefaults() {
                const defaults = {
                    modern: {
                        bgColor: 'linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%)',
                        fgColor: null // Uses CSS classes
                    },
                    retro: {
                        bgColor: 'linear-gradient(45deg, #2d1b69 0%, #11052c 50%, #0a0a0a 100%)',
                        fgColor: null
                    },
                    corporate: {
                        bgColor: 'linear-gradient(180deg, #f8f9fa 0%, #e9ecef 50%, #dee2e6 100%)',
                        fgColor: null
                    },
                    terminal: {
                        bgColor: '#000000',
                        fgColor: null
                    }
                };
                return defaults[this.config.variation] || defaults.modern;
            }
            /**
             * Load CSSOverride
             */
            loadCSSOverride() {
                var _this = this;
                // Remove any existing override CSS
                const existing_override = document.getElementById('css-override');
                if (existing_override) {
                    existing_override.remove();
                }

                // Create and load new override CSS
                const link = document.createElement('link');
                link.id = 'css-override';
                link.rel = 'stylesheet';
                link.type = 'text/css';
                link.href = window.fs42Api.urlFor(this.config.cssOverride);

                // Add error handling
                link.onerror = function () {
                    console.warn('Failed to load CSS override:', _this.config.cssOverride);
                };
                link.onload = function () {
                    console.log('CSS override loaded successfully:', _this.config.cssOverride);
                };

                // Append to head to ensure it loads after base styles
                document.head.appendChild(link);
            }
            /**
             * Load Next Up Shows
             */
            async loadNextUpShows() {
                try {
                    const now = new Date();
                    const end_time = new Date(now.getTime() + 4 * 60 * 60 * 1000); // 4 hours from now

                    // Format dates for API (YYYY-MM-DDTHH:MM:SS)
                    const formatDateForAPI = function (date) {
                        const year = date.getFullYear();
                        const month = String(date.getMonth() + 1).padStart(2, '0');
                        const day = String(date.getDate()).padStart(2, '0');
                        const hours = String(date.getHours()).padStart(2, '0');
                        const minutes = String(date.getMinutes()).padStart(2, '0');
                        const seconds = String(date.getSeconds()).padStart(2, '0');
                        return '' + year + '-' + month + '-' + day + 'T' + hours + ':' + minutes + ':' + seconds;
                    };

                    // Fetch schedule blocks using common.js function
                    const schedule_blocks = await window.fs42Common.fetchSchedule(
                        this.config.nextUp,
                        formatDateForAPI(now),
                        formatDateForAPI(end_time)
                    );
                    if (schedule_blocks && schedule_blocks.length > 0) {
                        const current_show = schedule_blocks.find(function (block) {
                            return new Date(block.start_time) <= now;
                        });
                        const upcoming_shows = schedule_blocks.filter(function (block) {
                            return new Date(block.start_time) > now;
                        });

                        // Check if we're within 5 minutes of the current show ending
                        let near_end = false;
                        if (current_show) {
                            const current_end = current_show.end_time
                                ? new Date(current_show.end_time)
                                : upcoming_shows.length > 0
                                  ? new Date(upcoming_shows[0].start_time)
                                  : null;
                            if (current_end) {
                                near_end = current_end - now <= 5 * 60 * 1000;
                            }
                        }
                        const detail_elements = [this.detailLine1, this.detailLine2, this.detailLine3];
                        const shows_to_display = [];
                        if (current_show && !near_end) {
                            // Show current show labeled "NOW" plus next 2
                            shows_to_display.push({
                                label: 'Now',
                                show: current_show
                            });
                            upcoming_shows.slice(0, 2).forEach(function (show) {
                                return shows_to_display.push({
                                    label: null,
                                    show
                                });
                            });
                        }
                        else {
                            // Near end or no current show: show next 3 upcoming
                            upcoming_shows.slice(0, 3).forEach(function (show) {
                                return shows_to_display.push({
                                    label: null,
                                    show
                                });
                            });
                        }
                        shows_to_display.forEach(function ({ label, show }, index) {
                            if (detail_elements[index]) {
                                const start_time = new Date(show.start_time);
                                const time_str =
                                    label ||
                                    start_time.toLocaleTimeString('en-US', {
                                        hour: 'numeric',
                                        minute: '2-digit',
                                        hour12: true
                                    });
                                detail_elements[index].textContent =
                                    '' + time_str + ' - ' + (show.title || 'Untitled');
                                detail_elements[index].style.display = 'block';
                            }
                        });

                        // Hide unused detail lines
                        for (let i = shows_to_display.length; i < detail_elements.length; i++) {
                            if (detail_elements[i]) {
                                detail_elements[i].style.display = 'none';
                            }
                        }
                    }
                    else {
                        // No upcoming shows found, show default message
                        this.detailLine1.textContent = 'No upcoming shows';
                        this.detailLine1.style.display = 'block';
                        this.detailLine2.style.display = 'none';
                        this.detailLine3.style.display = 'none';
                    }
                }
                catch (error) {
                    console.error('Error loading next up shows:', error);
                    // Fallback to showing error message
                    this.detailLine1.textContent = 'Schedule unavailable';
                    this.detailLine1.style.display = 'block';
                    this.detailLine2.style.display = 'none';
                    this.detailLine3.style.display = 'none';
                }
            }
            /**
             * Update Content Area To Video Bounds
             */
            updateContentAreaToVideoBounds() {
                if (!this.bgVideoPlayer || !this.contentArea || !this.config.backgroundVideo) {
                    return;
                }
                const video_width = this.bgVideoPlayer.videoWidth;
                const video_height = this.bgVideoPlayer.videoHeight;
                if (!video_width || !video_height) {
                    return;
                }
                const container_width = this.container.clientWidth;
                const container_height = this.container.clientHeight;
                const video_aspect = video_width / video_height;
                const container_aspect = container_width / container_height;
                let rendered_width;
                let rendered_height;
                if (container_aspect > video_aspect) {
                    rendered_height = container_height;
                    rendered_width = rendered_height * video_aspect;
                }
                else {
                    rendered_width = container_width;
                    rendered_height = rendered_width / video_aspect;
                }
                const left = (container_width - rendered_width) / 2;
                const top = (container_height - rendered_height) / 2;
                this.contentArea.style.width = '' + rendered_width + 'px';
                this.contentArea.style.height = '' + rendered_height + 'px';
                this.contentArea.style.left = '' + left + 'px';
                this.contentArea.style.top = '' + top + 'px';
            }
            /**
             * Clear Text Loop Timers
             */
            clearTextLoopTimers() {
                this.textLoopTimers.forEach(function (timer) {
                    return clearTimeout(timer);
                });
                this.textLoopTimers = [];
            }
            /**
             * Schedule Text For Video Loop
             */
            scheduleTextForVideoLoop() {
                var _this2 = this;
                if (!this.contentArea || !this.bgVideoPlayer || !this.config.backgroundVideo) {
                    return;
                }
                this.clearTextLoopTimers();
                const video_duration = this.bgVideoPlayer.duration;
                if (!video_duration || !isFinite(video_duration)) {
                    return;
                }
                const delay_sec = Math.max(parseFloat(this.config.textDelay) || 0, 0);
                const fade_in_sec = Math.max(parseFloat(this.config.textFadeIn) || 0, 0);
                const fade_out_sec = Math.max(parseFloat(this.config.textFadeOut) || 0, 0);
                const hide_before_end_sec = Math.max(parseFloat(this.config.textHideBeforeEnd) || 0, 0);

                // Start every video loop with text hidden.
                this.contentArea.style.opacity = '0';
                this.contentArea.style.transition = 'none';

                // Show text after text_delay.
                this.textLoopTimers.push(
                    setTimeout(function () {
                        _this2.contentArea.style.transition =
                            fade_in_sec > 0 ? 'opacity ' + fade_in_sec + 's ease-in' : 'none';
                        _this2.contentArea.style.opacity = '1';
                    }, delay_sec * 1000)
                );

                // Hide text before the end of the current video loop.
                if (hide_before_end_sec > 0) {
                    const fade_start_sec = Math.max(video_duration - hide_before_end_sec - fade_out_sec, 0);
                    this.textLoopTimers.push(
                        setTimeout(function () {
                            _this2.contentArea.style.transition =
                                fade_out_sec > 0 ? 'opacity ' + fade_out_sec + 's ease-out' : 'none';
                            _this2.contentArea.style.opacity = '0';
                        }, fade_start_sec * 1000)
                    );
                }
            }
            /**
             * Setup Text Presentation
             */
            setupTextPresentation() {
                var _this3 = this;
                if (!this.contentArea) {
                    return;
                }
                if (this.config.textPosition) {
                    this.container.classList.add('text-position-' + this.config.textPosition);
                }
                if (this.config.backgroundVideo) {
                    this.contentArea.style.opacity = '0';
                    return;
                }
                const delay_ms = Math.max(parseFloat(this.config.textDelay) || 0, 0) * 1000;
                const fade_in_sec = Math.max(parseFloat(this.config.textFadeIn) || 0, 0);
                this.contentArea.style.opacity = '0';
                this.contentArea.style.transition =
                    fade_in_sec > 0 ? 'opacity ' + fade_in_sec + 's ease-in' : 'none';
                setTimeout(function () {
                    _this3.contentArea.style.opacity = '1';
                }, delay_ms);
            }
            /**
             * Setup Background Video
             */
            setupBackgroundVideo() {
                var _this4 = this;
                if (!this.config.backgroundVideo || !this.bgVideoPlayer) {
                    return;
                }
                this.videoLoopsRemaining = Math.max(parseInt(this.config.backgroundVideoLoopCount) || 1, 1);
                this.bgVideoPlayer.src = window.fs42Api.urlFor(this.config.backgroundVideo);
                this.bgVideoPlayer.style.display = 'block';
                this.bgVideoPlayer.playsInline = true;
                this.bgVideoPlayer.loop = false;

                // If bg_music is set, keep video audio muted so audio behavior remains predictable.
                // Otherwise, use video audio unless bg_video_audio=false.
                this.bgVideoPlayer.muted = !!this.config.bgMusic || !this.config.backgroundVideoAudio;
                this.container.classList.add('video-bg');
                this.bgVideoPlayer.addEventListener('error', function () {
                    const error = _this4.bgVideoPlayer.error;
                    console.warn(
                        'Background video element error:',
                        error ? error.code : 'unknown',
                        error ? error.message : ''
                    );
                });
                this.bgVideoPlayer.addEventListener('loadedmetadata', function () {
                    _this4.updateContentAreaToVideoBounds();
                });
                window.addEventListener('resize', function () {
                    _this4.updateContentAreaToVideoBounds();
                });
                this.bgVideoPlayer.addEventListener('ended', function () {
                    if (_this4.config.duration > 0) {
                        _this4.bgVideoPlayer.currentTime = 0;
                        _this4.scheduleTextForVideoLoop();
                        _this4.playBackgroundVideo();
                        return;
                    }
                    _this4.videoLoopsRemaining--;
                    if (_this4.videoLoopsRemaining > 0) {
                        _this4.bgVideoPlayer.currentTime = 0;
                        _this4.scheduleTextForVideoLoop();
                        _this4.playBackgroundVideo();
                    }
                });
                this.bgVideoPlayer.addEventListener(
                    'canplay',
                    function () {
                        _this4.playBackgroundVideo();
                    },
                    {
                        once: true
                    }
                );
                this.bgVideoPlayer.load();
            }
            /**
             * Play Background Video
             */
            playBackgroundVideo() {
                var _this5 = this;
                if (!this.bgVideoPlayer) {
                    return;
                }
                this.bgVideoPlayer
                    .play()
                    .then(function () {
                        console.log('Background video started successfully');
                        _this5.scheduleTextForVideoLoop();
                    })
                    .catch(function (error) {
                        console.warn(
                            'Background video autoplay failed:',
                            error && error.name ? error.name : error,
                            error && error.message ? error.message : ''
                        );

                        // If unmuted autoplay is blocked, retry muted so the visual bump still plays.
                        if (!_this5.bgVideoPlayer.muted) {
                            _this5.bgVideoPlayer.muted = true;
                            _this5.bgVideoPlayer
                                .play()
                                .then(function () {
                                    console.log('Background video started muted after autoplay retry');
                                    _this5.scheduleTextForVideoLoop();
                                })
                                .catch(function (retry_error) {
                                    console.warn(
                                        'Background video muted retry failed:',
                                        retry_error && retry_error.name ? retry_error.name : retry_error,
                                        retry_error && retry_error.message ? retry_error.message : ''
                                    );
                                });
                        }
                    });
            }
            /**
             * Setup Countdown
             */
            setupCountdown() {
                var _this6 = this;
                if (!this.config.countdown || this.config.duration <= 0) {
                    return;
                }
                this.countdownTimer.style.display = 'block';
                const total_ms = this.config.duration;
                const start_time = Date.now();
                const update = function () {
                    const elapsed = Date.now() - start_time;
                    const remaining = Math.max(0, total_ms - elapsed);
                    const total_secs = Math.ceil(remaining / 1000);
                    const mins = Math.floor(total_secs / 60);
                    const secs = total_secs % 60;
                    _this6.countdownDisplay.textContent = '' + mins + ':' + String(secs).padStart(2, '0');
                    if (remaining > 0) {
                        requestAnimationFrame(update);
                    }
                };
                requestAnimationFrame(update);
            }
            /**
             * Setup Auto Hide
             */
            setupAutoHide() {
                var _this7 = this;
                if (this.config.duration > 0) {
                    // Enforce minimum duration of 2 seconds (2000ms)
                    const adjusted_duration = Math.max(this.config.duration, 2000);

                    // Start fade animation 1 second early so total duration matches exactly
                    const fade_start_time = Math.max(adjusted_duration - 1000, 0);

                    // Non-video autobumps can hide text relative to the bump duration.
                    // Video autobumps handle text hide/show per video loop.
                    if (!this.config.backgroundVideo && this.contentArea && this.config.textHideBeforeEnd > 0) {
                        const fade_out_sec = Math.max(parseFloat(this.config.textFadeOut) || 0, 0);
                        const hide_before_end_ms = this.config.textHideBeforeEnd * 1000;
                        const fade_out_ms = fade_out_sec * 1000;
                        const text_fade_start_time = Math.max(
                            adjusted_duration - hide_before_end_ms - fade_out_ms,
                            0
                        );
                        setTimeout(function () {
                            _this7.contentArea.style.transition =
                                fade_out_sec > 0 ? 'opacity ' + fade_out_sec + 's ease-out' : 'none';
                            _this7.contentArea.style.opacity = '0';
                        }, text_fade_start_time);
                    }
                    setTimeout(function () {
                        _this7.fadeOut();
                    }, fade_start_time);
                }
            }
            /**
             * Fade Out
             */
            fadeOut() {
                var _this8 = this;
                this.clearTextLoopTimers();
                if (this.contentArea && this.config.textFadeOut > 0) {
                    this.contentArea.style.transition = 'opacity ' + this.config.textFadeOut + 's ease-out';
                    this.contentArea.style.opacity = '0';
                }
                this.container.style.transition = 'opacity 1s ease-out';
                this.container.style.opacity = '0';
                setTimeout(function () {
                    _this8.container.style.display = 'none';
                }, 1000);
            }
            /**
             * Setup Background Music
             */
            setupBackgroundMusic() {
                var _this9 = this;
                if (this.config.bgMusic && this.bgMusicPlayer) {
                    this.bgMusicPlayer.src = window.fs42Api.urlFor(this.config.bgMusic);
                    this.bgMusicPlayer.loop = this.config.loopMusic;
                    this.bgMusicPlayer.volume = 0.3; // Set a reasonable default volume

                    // Try to play the music
                    this.bgMusicPlayer
                        .play()
                        .then(function () {
                            console.log('Background music started successfully');
                        })
                        .catch(function (error) {
                            console.warn('Background music autoplay failed:', error);
                            // This is expected in some browsers - the web render system handles autoplay
                        });

                    // Fade out music when bump fades out
                    const original_fade_out = this.fadeOut.bind(this);
                    this.fadeOut = function () {
                        _this9.fadeOutMusic();
                        original_fade_out();
                    };
                }
            }
            /**
             * Fade Out Music
             */
            fadeOutMusic() {
                var _this0 = this;
                if (this.bgMusicPlayer && !this.bgMusicPlayer.paused) {
                    const fade_interval = setInterval(function () {
                        if (_this0.bgMusicPlayer.volume > 0.05) {
                            _this0.bgMusicPlayer.volume = Math.max(0, _this0.bgMusicPlayer.volume - 0.05);
                        }
                        else {
                            _this0.bgMusicPlayer.pause();
                            _this0.bgMusicPlayer.volume = 0.3; // Reset for next time
                            clearInterval(fade_interval);
                        }
                    }, 50); // Fade over ~1 second
                }
            }

            // Static method to create bump with URL parameters
            /**
             * From URLParams
             */
            static fromURLParams() {
                const params = new URLSearchParams(window.location.search);
                const config = {
                    title: params.get('title') || 'FieldStation42',
                    subtitle: params.get('subtitle') || 'Its Up to you!',
                    details: [
                        params.get('detail1') || 'Big time watching is here!',
                        params.get('detail2') || 'Broadcasting 24/7',
                        params.get('detail3') || 'Sweet.'
                    ].filter(Boolean),
                    backgroundImage: params.get('bg') || null,
                    backgroundVideo: params.get('bg_video') || null,
                    backgroundVideoLoopCount: parseInt(params.get('bg_video_loop_count')) || 1,
                    backgroundVideoAudio: params.get('bg_video_audio') !== 'false',
                    backgroundColor: params.get('bgcolor') || '#000000',
                    bgColor: params.get('bg_color') || null,
                    fgColor: params.get('fg_color') || null,
                    theme: params.get('theme') || 'dark',
                    accentColor: params.get('accent') || 'white',
                    duration: parseInt(params.get('duration')) || 0,
                    nextUp: params.get('next_network') || null,
                    variation: params.get('variation') || 'modern',
                    cssOverride: params.get('css') || null,
                    bgMusic: params.get('bg_music') || null,
                    loopMusic: params.get('loopmusic') !== 'false',
                    countdown: params.get('countdown') === 'true',
                    textPosition: params.get('text_position') || null,
                    textDelay: parseFloat(params.get('text_delay')) || 0,
                    textFadeIn: parseFloat(params.get('text_fade_in')) || 0,
                    textFadeOut: parseFloat(params.get('text_fade_out')) || 0,
                    textHideBeforeEnd: parseFloat(params.get('text_hide_before_end')) || 0
                };
                return new StationBump(config);
            }

            // Method to update content dynamically
            /**
             * Update Content
             */
            async updateContent(new_config) {
                Object.assign(this.config, new_config);
                await this.applyConfiguration();
                this.setupTextPresentation();
            }
        }

        // API for external control
        window.StationBump = StationBump;

        // Global configuration function
        window.configureBump = async function (config) {
            if (window.currentBump) {
                await window.currentBump.updateContent(config);
            }
            else {
                window.currentBump = new StationBump(config);
            }
        };

        // Initialize bump on page load
        document.addEventListener('DOMContentLoaded', function () {
            // Check if URL parameters are provided
            const has_params = window.location.search.length > 0;
            if (has_params) {
                window.currentBump = StationBump.fromURLParams();
            }
            else {
                // Default configuration for FieldStation42
                window.currentBump = new StationBump();
            }
        });

        // Example usage in console:
        // configureBump({
        //     title: 'RETRO FM',
        //     subtitle: 'Classic Hits Radio',
        //     details: ['98.5 FM', 'Your Music Station', 'retrofm.com'],
        //     accentColor: 'blue',
        //     backgroundImage: 'background.jpg'
        // });
    };
    return self;
})();
