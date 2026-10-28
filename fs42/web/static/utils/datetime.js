/* This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0. */

/** Format a time with optional compact or single-letter AM/PM suffixes. */
function formatTime(date, {locale='en-US', compact=true, short_suffix=false, ...options}={}) {
    let text = new Intl.DateTimeFormat(locale, {hour:'numeric', minute:'2-digit', hour12:true, ...options}).format(date);
    if (compact || short_suffix) text = text.replace(/\s/g, '').toLowerCase();
    if (short_suffix) text = text.replace(/am$/, 'a').replace(/pm$/, 'p');
    return text;
}

/** Format a local time range, optionally hiding zero minutes and the starting suffix. */
function formatTimeRange(start, end, {hide_zero_minutes=true, short_suffix=true, start_suffix=false}={}) {
    function label(date, suffix) {
        const hour = date.getHours() % 12 || 12;
        const minutes = date.getMinutes();
        let text = String(hour);
        if (!hide_zero_minutes || minutes !== 0) text += ':' + String(minutes).padStart(2, '0');
        if (suffix) {
            const period = date.getHours() >= 12 ? 'pm' : 'am';
            text += short_suffix ? period[0] : period;
        }
        return text;
    }
    return label(start, start_suffix) + '-' + label(end, true);
}

/** Format elapsed seconds as m:ss or h:mm:ss. */
function formatDuration(seconds=0) {
    const number = Number(seconds);
    const total = Number.isFinite(number) ? Math.max(0, Math.floor(number)) : 0;
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor(total % 3600 / 60);
    return (hours ? hours + ':' + String(minutes).padStart(2, '0') : String(minutes))
        + ':' + String(total % 60).padStart(2, '0');
}

/** Serialize local date/time fields as YYYY-MM-DDTHH:mm:ss without a timezone suffix. */
function formatLocalDateTime(date) {
    const pad = value => String(value).padStart(2, '0');
    return String(date.getFullYear()).padStart(4, '0') + '-' + pad(date.getMonth() + 1) + '-' + pad(date.getDate())
        + 'T' + pad(date.getHours()) + ':' + pad(date.getMinutes()) + ':' + pad(date.getSeconds());
}

/** Build time intervals starting at a local interval boundary, with an optional interval offset. */
function computeTimeSlots(date=new Date(), {interval=30, count=4, offset=0}={}) {
    if (!Number.isInteger(interval) || interval <= 0 || !Number.isInteger(count) || count < 0 || !Number.isInteger(offset)) {
        throw new RangeError('Time slots require a positive integer interval, nonnegative count, and integer offset.');
    }
    const base = new Date(date.getTime());
    const minutes = base.getHours() * 60 + base.getMinutes();
    base.setHours(0, Math.floor(minutes / interval) * interval + offset * interval, 0, 0);
    return Array.from({length:count}, (_, index) => {
        const start = new Date(base.getTime() + index * interval * 60000);
        return {start, end:new Date(start.getTime() + interval * 60000)};
    });
}
