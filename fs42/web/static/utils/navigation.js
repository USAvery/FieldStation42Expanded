/* This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0. */

/** Resolve physical keys using the same catalog that validates remote actions. */
function navigationAction(event) {
    const keys = window.fs42Controls?.keys;
    return keys && Object.prototype.hasOwnProperty.call(keys, event.key) ? keys[event.key] : null;
}

/** Navigate rendered geometry rather than duplicating CSS column counts in JavaScript. */
class SpatialNavigator {
    constructor({getItems, getSelected, onSelect}) {
        this.getItems = getItems;
        this.getSelected = getSelected;
        this.onSelect = onSelect;
    }

    move(direction) {
        const items = Array.from(this.getItems());
        const selected = this.getSelected();
        const current = items[selected];
        if (!current) return this.selectFirst(items);
        const origin = current.getBoundingClientRect();
        const horizontal = direction === 'left' || direction === 'right';
        const sign = direction === 'left' || direction === 'up' ? -1 : 1;
        const center = rect => horizontal ? (rect.left + rect.right) / 2 : (rect.top + rect.bottom) / 2;
        const cross = rect => horizontal ? (rect.top + rect.bottom) / 2 : (rect.left + rect.right) / 2;
        const candidates = items.flatMap((item, index) => {
            if (item === current || item.disabled) return [];
            const rect = item.getBoundingClientRect();
            if (!rect.width || !rect.height) return [];
            const primary = (center(rect) - center(origin)) * sign;
            if (primary <= 1) return [];
            const overlap = horizontal
                ? rect.top < origin.bottom && rect.bottom > origin.top
                : rect.left < origin.right && rect.right > origin.left;
            return [{index, score:[overlap ? 0 : 1, primary, Math.abs(cross(rect) - cross(origin))]}];
        });
        candidates.sort((a,b) => {
            for (let i=0; i<a.score.length; i++) if (a.score[i] !== b.score[i]) return a.score[i] - b.score[i];
            return a.index - b.index;
        });
        if (candidates.length) this.onSelect(candidates[0].index);
        return candidates.length ? candidates[0].index : selected;
    }

    selectFirst(items=Array.from(this.getItems())) {
        const index = items.findIndex(item => this.isAvailable(item));
        if (index >= 0) this.onSelect(index);
        return index;
    }

    selectLast() {
        const items = Array.from(this.getItems());
        const reverseIndex = items.slice().reverse().findIndex(item => this.isAvailable(item));
        const index = reverseIndex < 0 ? -1 : items.length - 1 - reverseIndex;
        if (index >= 0) this.onSelect(index);
        return index;
    }

    isAvailable(item) {
        const rect = item.getBoundingClientRect();
        return !item.disabled && rect.width > 0 && rect.height > 0;
    }
}
