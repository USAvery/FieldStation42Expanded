#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Present an overlay through the shared display service without launching another Qt application
"""
from fs42.tools.display.client import get_client
from fs42.tools.overlay._utils import OverlayError


class Overlay(object):
    """
    Select and show one presentation in the shared display process
    """

    def __init__(self, overlay_type, **options):
        """
        Retain a supported panel type and its display inputs

        :param overlay_type: (str) now_playing, ticker, parental_controls, or media_info
        :param options:      (dict) JSON-compatible display constructor arguments
        """
        self._overlay_type = overlay_type
        self._options = options
        self._check_args()

    def _check_args(self):
        """
        Reject unsupported display types before contacting the service
        """
        if self._overlay_type not in ('now_playing', 'ticker', 'parental_controls', 'media_info'):
            raise OverlayError('Unknown overlay type: {}'.format(self._overlay_type))

    def start(self):
        """
        Show this panel and return its handle without allocating another display process
        """
        return get_client().show(self._overlay_type, **self._options)

    def run(self):
        """
        Keep a command-line presentation alive until it finishes or the caller is interrupted

        :return: (int) zero for completion, or one when a duplicate ticker is rejected
        """
        from fs42.tools.display.client import get_client
        try:
            panel = self.start()
            panel.wait()
            return 0 if panel.accepted else 1
        finally:
            get_client().close()
