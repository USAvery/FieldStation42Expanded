/*
This Source Code Form is subject to the Mozilla Public License, v. 2.0.
See https://mozilla.org/MPL/2.0/.
*/
window.app = window.app || {};
app.menu = app.menu || {};
app.menu.ppv = (function () {
    let self = {};

    /**
     * Random Other Index
     */
    self.randomOtherIndex = function(playlist, current) {
        if (playlist.length <= 1) {
            return 0;
        }
        let next;
        do {
            next = Math.floor(Math.random() * playlist.length);
        } while (next === current);
        return next;
    };
    class PPVViewer {
        /**
         * Constructor
         */
        constructor(config = {}) {
            // Container elements
            this.container = document.getElementById('ppvContainer');
            this.backgroundLayer = document.getElementById('backgroundLayer');
            this.loadingOverlay = document.getElementById('loadingOverlay');

            // Display elements
            this.currentImage = document.getElementById('currentImage');
            this.noImage = document.getElementById('noImage');
            this.contentTitle = document.getElementById('contentTitle');
            this.contentDetails = document.getElementById('contentDetails');
            this.contentDescription = document.getElementById('contentDescription');
            this.slideCounter = document.getElementById('slideCounter');
            this.config = {
                channelNumber: null,
                variation: 'modern',
                cssOverride: null,
                backgroundImage: null,
                bgColor: null,
                slideDuration: 10000,
                // 10 seconds per slide
                musicPath: null,
                randomMusic: true,
                ...config
            };
            this.contents = [];
            this.currentIndex = 0;
            this.slideshowTimer = null;
            this.slideDirection = 'up'; // Track slide direction: 'up' or 'down'

            // Music playlist
            this.bgMusicPlayer = document.getElementById('bgMusicPlayer');
            this.musicPlaylist = [];
            this.currentMusicIndex = 0;
            this.init();
        }
        /**
         * Init
         */
        async init() {
            await this.loadTheme(this.config.variation);
            await this.loadContent();
            await this.loadMusicPlaylist();
            this.setupKeyboardNavigation();
            this.applyConfiguration();
            this.setupBackgroundMusic();
            this.startSlideshow();
        }
        /**
         * Load Theme
         */
        loadTheme(name) {
            return new Promise(function (resolve) {
                const link = document.createElement('link');
                link.rel = 'stylesheet';
                link.href = 'themes/' + name + '.css';
                link.addEventListener('load', resolve);
                link.addEventListener('error', function () {
                    console.warn('PPV theme "' + name + '" not found, using defaults.');
                    resolve();
                });
                document.head.appendChild(link);
            });
        }
        /**
         * Load Content
         */
        async loadContent() {
            if (!this.config.channelNumber) {
                this.showError('No channel number specified');
                return;
            }
            try {
                // Build API URL
                let api_url = 'ppv/' + this.config.channelNumber;
                if (this.config.variation && this.config.variation !== 'modern') {
                    api_url += '?variation=' + encodeURIComponent(this.config.variation);
                }
                const response = await apiGet(api_url);

                // Store contents
                this.contents = response.contents || [];

                // Hide loading overlay
                this.loadingOverlay.classList.add('hidden');

                // Show first slide
                if (this.contents.length > 0) {
                    this.showSlide(0);
                }
                else {
                    this.showError('No content available');
                }
            }
            catch (error) {
                console.error('Error loading PPV content:', error);
                this.showError('Failed to load content: ' + (error.message || 'Unknown error'));
            }
        }
        /**
         * Show Slide
         */
        showSlide(index) {
            var _this = this;
            if (index < 0 || index >= this.contents.length) {
                return;
            }
            this.currentIndex = index;
            const content = this.contents[index];

            // Update slide counter
            this.slideCounter.textContent = '' + (index + 1) + '/' + this.contents.length;

            // Update text content
            this.contentTitle.textContent = content.nfo?.title || content.filename;
            this.contentDetails.textContent = content.nfo?.info || '';
            this.contentDescription.textContent = content.nfo?.description || '';

            // Update image with vertical slide effect
            if (content.has_image && content.image_url) {
                // Slide out current image in the appropriate direction
                const slide_out_class = this.slideDirection === 'up' ? 'slide-out-up' : 'slide-out-down';
                const slide_in_class = this.slideDirection === 'up' ? 'slide-in-up' : 'slide-in-down';
                this.currentImage.classList.add(slide_out_class);
                setTimeout(function () {
                    // Reset all transition classes
                    _this.currentImage.classList.remove(
                        'visible',
                        'slide-out-up',
                        'slide-out-down',
                        'slide-in-up',
                        'slide-in-down'
                    );

                    // Load new image
                    _this.currentImage.src = urlFor(content.image_url);

                    // Start with slide-in position
                    _this.currentImage.classList.add(slide_in_class);
                    _this.currentImage.style.display = 'block';
                    _this.noImage.classList.remove('visible');

                    // Force reflow to ensure transition works
                    _this.currentImage.offsetHeight;

                    // Slide in to visible position
                    _this.currentImage.classList.remove(slide_in_class);
                    _this.currentImage.classList.add('visible');

                    // Handle image load errors
                    _this.currentImage.onerror = function () {
                        console.warn('Failed to load image:', content.image_url);
                        _this.currentImage.classList.remove('visible');
                        _this.currentImage.style.display = 'none';
                        _this.noImage.classList.add('visible');
                    };
                }, 500); // Wait for slide out
            }
            else {
                // No image available
                this.currentImage.classList.remove('visible');
                this.currentImage.style.display = 'none';
                this.noImage.classList.add('visible');
            }
        }
        /**
         * Start Slideshow
         */
        startSlideshow() {
            var _this2 = this;
            // Clear any existing timer
            if (this.slideshowTimer) {
                clearInterval(this.slideshowTimer);
            }

            // Auto-advance every 10 seconds (or configured duration)
            this.slideshowTimer = setInterval(function () {
                _this2.nextSlide();
            }, this.config.slideDuration);
        }
        /**
         * Stop Slideshow
         */
        stopSlideshow() {
            if (this.slideshowTimer) {
                clearInterval(this.slideshowTimer);
                this.slideshowTimer = null;
            }
        }
        /**
         * Next Slide
         */
        nextSlide() {
            if (this.contents.length === 0) {
                return;
            }
            this.slideDirection = 'up'; // Moving to next slides up
            const next_index = (this.currentIndex + 1) % this.contents.length;
            this.showSlide(next_index);
        }
        /**
         * Previous Slide
         */
        previousSlide() {
            if (this.contents.length === 0) {
                return;
            }
            this.slideDirection = 'down'; // Moving to previous slides down
            const prev_index = (this.currentIndex - 1 + this.contents.length) % this.contents.length;
            this.showSlide(prev_index);
        }
        /**
         * Setup Keyboard Navigation
         */
        setupKeyboardNavigation() {
            var _this3 = this;
            document.addEventListener('keydown', function (e) {
                switch (e.key) {
                    case 'PageUp':
                        e.preventDefault();
                        _this3.nextSlide();
                        // Reset slideshow timer
                        _this3.startSlideshow();
                        break;
                    case 'PageDown':
                        e.preventDefault();
                        _this3.previousSlide();
                        // Reset slideshow timer
                        _this3.startSlideshow();
                        break;
                    case 'Enter':
                        e.preventDefault();
                        _this3.confirmSelection();
                        break;
                    case 'p':
                    case 'P':
                        // Pause/resume slideshow
                        e.preventDefault();
                        if (_this3.slideshowTimer) {
                            _this3.stopSlideshow();
                            console.log('Slideshow paused');
                        }
                        else {
                            _this3.startSlideshow();
                            console.log('Slideshow resumed');
                        }
                        break;
                }
            });
        }
        /**
         * Confirm Selection
         */
        async confirmSelection() {
            if (this.contents.length === 0) {
                return;
            }
            const selected_content = this.contents[this.currentIndex];
            if (!selected_content) {
                return;
            }
            console.log('Content selected:', selected_content);

            // Stop slideshow while playing
            this.stopSlideshow();
            try {
                // Call the play_file API
                const response = await apiPost('ppv/' + this.config.channelNumber + '/play_file', {
                    file_path: selected_content.video_path
                });
                console.log('Play command sent:', response);

                // Optionally show a brief confirmation
                // For now, we'll just log it - the video should start playing
                // When the video ends, the player will return to the PPV channel
                // and the slideshow will resume automatically
            }
            catch (error) {
                console.error('Error sending play command:', error);
                alert(
                    'Failed to play: ' + (error.detail || error.message) + '\n\nPress OK to resume slideshow.'
                );
                // Resume slideshow on error
                this.startSlideshow();
            }
        }
        /**
         * Apply Configuration
         */
        applyConfiguration() {
            var _this4 = this;
            // Set background image or color from URL params
            if (this.config.backgroundImage) {
                this.backgroundLayer.style.backgroundImage = 'url(' + this.config.backgroundImage + ')';
            }
            else if (this.config.bgColor) {
                this.container.style.background = this.config.bgColor;
            }

            // Load optional CSS override on top of the theme
            if (this.config.cssOverride) {
                const link = document.createElement('link');
                link.rel = 'stylesheet';
                link.href = urlFor(this.config.cssOverride);
                link.onerror = function () {
                    return console.warn('Failed to load CSS override:', _this4.config.cssOverride);
                };
                document.head.appendChild(link);
            }
        }
        /**
         * Show Error
         */
        showError(message) {
            this.loadingOverlay.classList.remove('hidden');
            this.loadingOverlay.innerHTML =
                '\n            <div class="loading-text" style="color: #ff4444;">\n                Error: ' +
                escapeHtml(message) +
                '\n            </div>\n        ';
        }
        /**
         * Load Music Playlist
         */
        async loadMusicPlaylist() {
            try {
                if (this.config.musicPath) {
                    const response = await fetchURL(
                        urlFor('api.media.list_media') + '?path=' + encodeURIComponent(this.config.musicPath) + '&type=audio'
                    );
                    if (!response.ok) {
                        throw new Error('HTTP error! status: ' + response.status);
                    }
                    const data = await response.json();
                    this.musicPlaylist = data.files || [];
                }
                else {
                    const response = await fetchURL('music_playlist.json');
                    if (!response.ok) {
                        throw new Error('HTTP error! status: ' + response.status);
                    }
                    const data = await response.json();
                    this.musicPlaylist = data.music_files || [];
                }
                console.log('Loaded music playlist:', this.musicPlaylist);
            }
            catch (error) {
                console.warn('Failed to load music playlist:', error);
                // Continue without music
                this.musicPlaylist = [];
            }
        }
        /**
         * Setup Background Music
         */
        setupBackgroundMusic() {
            var _this5 = this;
            if (!this.bgMusicPlayer || this.musicPlaylist.length === 0) {
                console.log('No background music available');
                return;
            }

            // Set initial volume
            this.bgMusicPlayer.volume = 0.3;

            // Load first track
            if (this.config.randomMusic) {
                this.playMusicTrack(Math.floor(Math.random() * this.musicPlaylist.length));
            }
            else {
                this.playMusicTrack(0);
            }

            // When a track ends, play the next one
            this.bgMusicPlayer.addEventListener('ended', function () {
                _this5.playNextTrack();
            });

            // Handle errors by skipping to next track
            this.bgMusicPlayer.addEventListener('error', function (e) {
                console.warn('Error loading music track:', _this5.musicPlaylist[_this5.currentMusicIndex], e);
                _this5.playNextTrack();
            });
        }
        /**
         * Play Music Track
         */
        playMusicTrack(index) {
            var _this6 = this;
            if (index < 0 || index >= this.musicPlaylist.length) {
                index = 0;
            }
            this.currentMusicIndex = index;
            this.bgMusicPlayer.src = urlFor(this.musicPlaylist[index]);

            // Try to play the music
            this.bgMusicPlayer
                .play()
                .then(function () {
                    console.log('Playing background music:', _this6.musicPlaylist[index]);
                })
                .catch(function (error) {
                    console.warn('Background music autoplay failed:', error);
                    // This is expected in some browsers - user interaction may be required
                });
        }
        /**
         * Play Next Track
         */
        playNextTrack() {
            if (this.config.randomMusic) {
                this.playMusicTrack(self.randomOtherIndex(this.musicPlaylist, this.currentMusicIndex));
                return;
            }
            // Loop back to first track after last one
            const next_index = (this.currentMusicIndex + 1) % this.musicPlaylist.length;
            this.playMusicTrack(next_index);
        }

        // Static method to create viewer from URL parameters
        /**
         * From URLParams
         */
        static fromURLParams() {
            const params = new URLSearchParams(window.location.search);
            const channel_number = params.get('channel');
            if (!channel_number) {
                console.error('No channel parameter provided');
                return null;
            }
            const config = {
                channelNumber: parseInt(channel_number),
                variation: params.get('variation') || 'modern',
                cssOverride: params.get('css') || null,
                backgroundImage: params.get('bg') || null,
                bgColor: params.get('bg_color') || null,
                slideDuration: parseInt(params.get('duration')) || 10000,
                musicPath: params.get('music') || null,
                randomMusic: params.get('random_music') !== 'false'
            };
            return new PPVViewer(config);
        }
    }

    window.PPVViewer = PPVViewer;

    /** Explain an absent channel without starting a viewer. */
    self.showMissingChannel = function() {
        document.getElementById('loadingOverlay').innerHTML = [
            '',
            '            <div class="loading-text" style="color: #ff4444;">',
            '                Error: No channel specified. Please add ?channel=XX to the URL',
            '            </div>',
            '        '
        ].join('\n');
    };

    /** Initialize the page and bind its controls. */
    self.setup = function() {
        window.currentPPVViewer = PPVViewer.fromURLParams();
        if (!window.currentPPVViewer) self.showMissingChannel();
    };
    return self;
})();
