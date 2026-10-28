/* This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0. */

/** Read a CSS custom property from an element, defaulting to the document root. */
function getCSSVar(name, element=document.documentElement) {
    return getComputedStyle(element).getPropertyValue(name).trim();
}
