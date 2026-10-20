/*
This Source Code Form is subject to the Mozilla Public License, v. 2.0.
See https://mozilla.org/MPL/2.0/.
*/
window.app = window.app || {};
app.tools = app.tools || {};
app.tools.diagnostics = (function () {
    let self = {};
    /**
     * Set up the diagnostics page
     */
    self.setup = function () {
        // Diagnostics slideshow functionality for CRT displays
        class DiagnosticsSlideshow {
            /**
             * Constructor
             */
            constructor() {
                this.slides = [];
                this.currentSlide = 0;
                this.slideInterval = null;
                this.slideDuration = 7000; // 7 seconds per slide
                this.diagnosticsData = null;
            }
            /**
             * Init
             */
            async init() {
                await this.loadDiagnosticsData();
                this.createSlides();
                this.startSlideshow();
                this.startTimestampUpdater();
            }
            /**
             * Load Diagnostics Data
             */
            async loadDiagnosticsData() {
                try {
                    this.showLoading();
                    this.diagnosticsData = await window.fs42Api.get('player/info');
                    this.hideLoading();
                }
                catch (error) {
                    this.showError('Failed to load diagnostics: ' + error.message);
                    console.error('Failed to load diagnostics:', error);
                }
            }
            /**
             * Create Slides
             */
            createSlides() {
                const container = document.getElementById('slideshow-container');
                container.innerHTML = '';
                this.slides = [];
                if (!this.diagnosticsData) {
                    return;
                }

                // Slide 1: System Information
                if (this.diagnosticsData.system) {
                    this.slides.push(
                        this.createSlide('SYSTEM INFORMATION', [
                            {
                                label: 'Platform',
                                value: this.diagnosticsData.system.platform || 'Unknown'
                            },
                            {
                                label: 'Architecture',
                                value: this.diagnosticsData.system.architecture || 'Unknown'
                            },
                            {
                                label: 'Hostname',
                                value: this.diagnosticsData.system.hostname || 'Unknown'
                            }
                        ])
                    );
                }

                // Slide 2: Temperature
                const temp_data = [];
                if (this.diagnosticsData.temperature_c !== undefined) {
                    const temp_class = this.getTemperatureClass(this.diagnosticsData.temperature_c);
                    temp_data.push({
                        label: 'CPU Temperature',
                        value: '' + this.diagnosticsData.temperature_c + '°C',
                        class: temp_class
                    });
                }
                if (this.diagnosticsData.temperature_f !== undefined) {
                    const temp_class = this.getTemperatureClass(this.diagnosticsData.temperature_c);
                    temp_data.push({
                        label: 'CPU Temperature',
                        value: '' + this.diagnosticsData.temperature_f + '°F',
                        class: temp_class
                    });
                }
                if (temp_data.length > 0) {
                    this.slides.push(this.createSlide('TEMPERATURE', temp_data));
                }

                // Slide 3: Memory Information
                if (this.diagnosticsData.memory) {
                    const mem_data = [];
                    if (this.diagnosticsData.memory.total_gb !== undefined) {
                        mem_data.push({
                            label: 'Total',
                            value: '' + this.diagnosticsData.memory.total_gb + ' GB'
                        });
                    }
                    if (this.diagnosticsData.memory.used_percent !== undefined) {
                        const mem_class = this.getMemoryClass(this.diagnosticsData.memory.used_percent);
                        mem_data.push({
                            label: 'Used',
                            value: '' + this.diagnosticsData.memory.used_percent + '%',
                            class: mem_class
                        });
                    }
                    if (this.diagnosticsData.memory.available_gb !== undefined) {
                        mem_data.push({
                            label: 'Available',
                            value: '' + this.diagnosticsData.memory.available_gb + ' GB'
                        });
                    }
                    if (mem_data.length > 0) {
                        this.slides.push(this.createSlide('MEMORY STATUS', mem_data));
                    }
                }

                // Slide 4: CPU Information
                if (this.diagnosticsData.cpu) {
                    const cpu_data = [];
                    if (this.diagnosticsData.cpu.cores !== undefined) {
                        cpu_data.push({
                            label: 'CPU Cores',
                            value: this.diagnosticsData.cpu.cores.toString()
                        });
                    }
                    if (this.diagnosticsData.cpu.load_percent !== undefined) {
                        cpu_data.push({
                            label: 'CPU Load',
                            value: '' + this.diagnosticsData.cpu.load_percent + '%'
                        });
                    }
                    if (this.diagnosticsData.cpu.load_1min !== undefined) {
                        cpu_data.push({
                            label: 'Load Avg',
                            value: this.diagnosticsData.cpu.load_1min.toFixed(2)
                        });
                    }
                    if (cpu_data.length > 0) {
                        this.slides.push(this.createSlide('CPU STATUS', cpu_data));
                    }
                }

                // Add all slides to container
                this.slides.forEach(function (slide, index) {
                    slide.style.display = index === 0 ? 'flex' : 'none';
                    container.appendChild(slide);
                });
            }
            /**
             * Create Slide
             */
            createSlide(title, data_items) {
                const slide = document.createElement('div');
                slide.className = 'slide';
                if (this.slides.length === 0) {
                    slide.classList.add('active');
                }

                // Header section
                const header = document.createElement('div');
                header.className = 'header';
                const slide_title = document.createElement('div');
                slide_title.className = 'title';
                slide_title.textContent = title;
                header.appendChild(slide_title);

                // Content section
                const content = document.createElement('div');
                content.className = 'content';

                // Limit to 3-4 items per slide for readability
                const items_to_show = data_items.slice(0, 4);
                items_to_show.forEach(function (item) {
                    const data_row = document.createElement('div');
                    data_row.className = 'data-row';
                    const label = document.createElement('div');
                    label.className = 'label';
                    label.textContent = item.label;
                    const value = document.createElement('div');
                    value.className = 'value';
                    value.textContent = item.value;

                    // Apply color classes for temperature and memory
                    if (item.class) {
                        value.classList.add(item.class);
                    }
                    data_row.appendChild(label);
                    data_row.appendChild(value);
                    content.appendChild(data_row);
                });

                // Footer section
                const footer = document.createElement('div');
                footer.className = 'footer';
                const page_info = document.createElement('div');
                page_info.className = 'page-info';
                page_info.textContent = 'FieldStation42';
                const timestamp = document.createElement('div');
                timestamp.className = 'timestamp';
                timestamp.textContent = new Date().toLocaleTimeString();
                footer.appendChild(page_info);
                footer.appendChild(timestamp);
                slide.appendChild(header);
                slide.appendChild(content);
                slide.appendChild(footer);
                return slide;
            }
            /**
             * Get Temperature Class
             */
            getTemperatureClass(temp_c) {
                if (temp_c > 75) {
                    return 'temp-high';
                }
                if (temp_c < 40) {
                    return 'temp-low';
                }
                return 'temp-normal';
            }
            /**
             * Get Memory Class
             */
            getMemoryClass(used_percent) {
                if (used_percent > 80) {
                    return 'memory-high';
                }
                if (used_percent < 50) {
                    return 'memory-low';
                }
                return 'memory-normal';
            }
            /**
             * Start Slideshow
             */
            startSlideshow() {
                var _this = this;
                if (this.slides.length <= 1) {
                    return;
                }
                this.slideInterval = setInterval(function () {
                    _this.nextSlide();
                }, this.slideDuration);
            }
            /**
             * Stop Slideshow
             */
            stopSlideshow() {
                if (this.slideInterval) {
                    clearInterval(this.slideInterval);
                    this.slideInterval = null;
                }
            }
            /**
             * Next Slide
             */
            nextSlide() {
                if (this.slides.length === 0) {
                    return;
                }

                // Hide current slide
                this.slides[this.currentSlide].style.display = 'none';
                this.slides[this.currentSlide].classList.remove('active');

                // Move to next slide
                this.currentSlide = (this.currentSlide + 1) % this.slides.length;

                // Show new slide
                this.slides[this.currentSlide].style.display = 'flex';
                this.slides[this.currentSlide].classList.add('active');
            }
            /**
             * Previous Slide
             */
            previousSlide() {
                if (this.slides.length === 0) {
                    return;
                }

                // Hide current slide
                this.slides[this.currentSlide].style.display = 'none';
                this.slides[this.currentSlide].classList.remove('active');

                // Move to previous slide
                this.currentSlide = this.currentSlide === 0 ? this.slides.length - 1 : this.currentSlide - 1;

                // Show new slide
                this.slides[this.currentSlide].style.display = 'flex';
                this.slides[this.currentSlide].classList.add('active');
            }
            /**
             * Show Loading
             */
            showLoading() {
                const container = document.getElementById('slideshow-container');
                container.innerHTML = [
                    '',
                    '            <div class="loading">',
                    '                <div class="loading-text">LOADING DIAGNOSTICS</div>',
                    '                <div class="loading-bar">',
                    '                    <div class="loading-fill"></div>',
                    '                </div>',
                    '            </div>',
                    '        '
                ].join('\n');
            }
            /**
             * Hide Loading
             */
            hideLoading() {
                // Loading will be replaced by slides
            }
            /**
             * Show Error
             */
            showError(message) {
                const container = document.getElementById('slideshow-container');
                container.innerHTML =
                    [
                        '',
                        '            <div class="error-message">',
                        '                <div class="error-title">SYSTEM ERROR</div>',
                        '                <div>'
                    ].join('\n') +
                    message +
                    '</div>\n            </div>\n        ';
            }
            /**
             * Start Timestamp Updater
             */
            startTimestampUpdater() {
                // Update timestamp every second
                setInterval(function () {
                    // Find the timestamp element in the currently active slide
                    const active_slide = document.querySelector('.slide.active');
                    if (active_slide) {
                        const timestamp_element = active_slide.querySelector('.timestamp');
                        if (timestamp_element) {
                            timestamp_element.textContent = new Date().toLocaleTimeString();
                        }
                    }
                }, 1000);
            }
            /**
             * Refresh
             */
            async refresh() {
                this.stopSlideshow();
                this.currentSlide = 0;
                await this.loadDiagnosticsData();
                this.createSlides();
                this.startSlideshow();
            }
        }

        // Global slideshow instance
        let diagnostics_slideshow;

        // Initialize when page loads
        document.addEventListener('DOMContentLoaded', async function () {
            diagnostics_slideshow = new DiagnosticsSlideshow();
            await diagnostics_slideshow.init();
        });

        // Keyboard controls for manual navigation
        document.addEventListener('keydown', function (event) {
            if (!diagnostics_slideshow) {
                return;
            }
            switch (event.key) {
                case 'ArrowRight':
                case ' ':
                case 'n':
                    event.preventDefault();
                    diagnostics_slideshow.nextSlide();
                    break;
                case 'ArrowLeft':
                case 'p':
                    event.preventDefault();
                    diagnostics_slideshow.previousSlide();
                    break;
                case 'r':
                case 'F5':
                    event.preventDefault();
                    diagnostics_slideshow.refresh();
                    break;
                case 'Escape':
                    event.preventDefault();
                    if (diagnostics_slideshow.slideInterval) {
                        diagnostics_slideshow.stopSlideshow();
                    }
                    else {
                        diagnostics_slideshow.startSlideshow();
                    }
                    break;
            }
        });

        // Auto-refresh every 30 seconds
        setInterval(function () {
            if (diagnostics_slideshow) {
                diagnostics_slideshow.refresh();
            }
        }, 30000);
    };
    return self;
})();
