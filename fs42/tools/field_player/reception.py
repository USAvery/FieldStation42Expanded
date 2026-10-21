#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Track simulated reception quality and produce MPV filters and transition effects for degraded
signals and channel changes.
"""
import time
import random

from fs42.core import logger as project_logger

_logger = project_logger.setup('fs42.tools.field_player.reception')

debounce_fragment = 0.1


def none_change_effect(player, reception):
    """
    Leave reception unchanged when channel-transition effects are disabled
    """
    _logger.info('No change effect applied.')
    pass


def short_change_effect(player, reception):
    """
    Briefly degrade reception before tuning by stepping the player's noise filter
    """
    _logger.info('Applying short change effect.')
    prev = reception.improve_amount
    reception.improve_amount = 0

    while not reception.is_degraded():
        reception.degrade(0.2)
        player.update_filters()
        time.sleep(debounce_fragment)

    reception.improve_amount = prev


def long_change_effect(player, reception):
    """
    Play static between degradation and recovery phases to simulate analog channel tuning
    """
    _logger.info('Applying long change effect.')
    # add noise to current channel
    while not reception.is_degraded():
        reception.degrade()
        player.update_filters()
        time.sleep(debounce_fragment)

    # reception.improve(1)
    player.play_file('runtime/static.mp4')
    while not reception.is_perfect():
        reception.improve()
        player.update_filters()
        time.sleep(debounce_fragment)
    # time.sleep(1)
    while not reception.is_degraded():
        reception.degrade()
        player.update_filters()
        time.sleep(debounce_fragment)


class ReceptionStatus(object):
    """
    Share simulated reception quality and derive the corresponding MPV video filter
    """
    __we_are_all_one = {}
    chaos = 0
    thresh = 0.01
    degrade_amount = 0.05
    improve_amount = 0.05

    # NOTE: This is the borg singleton pattern - __we_are_all_one
    def __new__(cls, *args, **kwargs):
        """
        Attach each reception object to the common quality-state dictionary
        """
        obj = super(ReceptionStatus, cls).__new__(cls, *args, **kwargs)
        obj.__dict__ = cls.__we_are_all_one
        return obj

    def __init__(self):
        """
        Reuse the reception state established by the shared instance allocation
        """
        pass

    def is_perfect(self):
        """
        Check whether simulated reception has no remaining noise
        """
        return self.chaos == 0.0

    def is_degraded(self):
        """
        Check whether reception noise exceeds the visible-effect threshold
        """
        return self.chaos > self.thresh

    def is_fully_degraded(self):
        """
        Check whether reception has reached its maximum noise level
        """
        return self.chaos == 1.0

    def degrade(self, override=0):
        """
        Increase reception noise by the supplied step or default amount, capped at one
        """
        if override == 0:
            self.chaos += self.degrade_amount
        else:
            self.chaos += override

        if self.chaos > 1.0:
            self.chaos = 1.0

    def improve(self, override=0):
        """
        Reduce reception noise and clear it when it falls below the effect threshold
        """
        if override == 0:
            self.chaos -= self.improve_amount
        else:
            self.chaos -= override

        if self.chaos < self.thresh:
            self.chaos = 0.0

    def filter(self):
        """
        Build an MPV noise-and-scroll filter for degraded reception, or return an empty filter
        """
        if self.chaos > self.thresh:
            # between 0 and 100
            noise = self.chaos * 100
            # between 0 and .5
            v_scroll = self.chaos * 0.5
            return 'lavfi=[noise=alls={0}:allf=t+u, scroll=h=0:v={1}]'.format(noise, v_scroll)
        else:
            return ''


class ScrambledVideoFilter(object):
    """
    Provide a no-effect base interface for periodically updated video scrambling
    """

    def __init__(self):
        """
        Create a stateless scrambling filter with no effect
        """
        pass

    def update_filter(self):
        """
        Return an empty MPV filter for the base scrambling implementation
        """
        return ''


class HLScrambledVideoFilter(ScrambledVideoFilter):
    """
    Distort alternating horizontal video bands with a changing sinusoidal displacement
    """

    def __init__(self):
        """
        Initialize horizontal-band distortion strength and wavelength
        """
        self.chaos = 50
        self.thrust = 20

    def update_filter(self):
        """
        Vary the horizontal-band distortion parameters and return its MPV filter expression
        """

        if random.random() > .95:
            self.chaos = random.randint(40, 70)
        if random.random() > .9:
            self.chaos = random.randint(10, 30)
        return "lavfi=[geq='if(mod(floor(Y/4),2),p(X,Y+{0}*sin(2*PI*X/{1})),p(X,Y))']".format(
            self.thrust, self.chaos)


class DiagonalScrambledVideoFilter(ScrambledVideoFilter):
    """
    Displace video rows horizontally to create a changing diagonal scrambling effect
    """

    def __init__(self):
        """
        Initialize the amplitude and wavelength of row displacement
        """
        self.chaos = 50
        self.thrust = 20

    def update_filter(self):
        """
        Vary row-displacement strength and return the diagonal scrambling filter
        """

        if random.random() > .95:
            self.chaos = random.randint(5, 15)
        if random.random() > .9:
            self.chaos = random.randint(20, 40)
        return "lavfi=[geq='p(X+{0}*sin(2*PI*Y/{1}),Y)']".format(self.chaos, self.thrust)


class ColorInvertedScrambledVideoFilter(ScrambledVideoFilter):
    """
    Alternate normal and inverted pixel bands to simulate scrambled television
    """

    def __init__(self):
        """
        Initialize the band spacing used by the inversion effect
        """
        self.chaos = 50
        self.thrust = 20

    def update_filter(self):
        """
        Occasionally vary band spacing and return the alternating inversion filter
        """

        if random.random() > .95:
            self.chaos = random.randint(8, 12)

        return "lavfi=[geq='if(mod(floor(Y/{}),2),255-p(X,Y),p(X,Y))']".format(self.chaos)


class ChunkyScrambledVideoFilter(ScrambledVideoFilter):
    """
    Distort low-resolution color channels independently to create blocky scrambled video
    """

    def __init__(self):
        """
        Create the stateless block-distortion filter
        """
        pass

    def update_filter(self):
        """
        Return the MPV filter chain that shifts low-resolution color bands independently
        """
        return "lavfi=[scale=320:240,split[base][aux];[aux]geq=r='p(X+floor((random(1000+floor(N*0.05)+floor(Y/16))-0.5)*W*0.4),Y)':g='p(X+floor((random(2000+floor(N*0.05)+floor(Y/16))-0.5)*W*0.4),Y)':b='p(X+floor((random(3000+floor(N*0.05)+floor(Y/16))-0.5)*W*0.4),Y)'[warped];[base][warped]overlay,scale=640:480]"
