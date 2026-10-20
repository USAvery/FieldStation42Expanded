#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Manage reception
"""
import time
import random

from fs42.core import logger as project_logger

_logger = project_logger.setup('fs42.tools.field_player.reception')

debounce_fragment = 0.1


def none_change_effect(player, reception):
    """
    None change effect
    """
    _logger.info('No change effect applied.')
    pass


def short_change_effect(player, reception):
    """
    Short change effect
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
    Long change effect
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
    ReceptionStatus
    """
    __we_are_all_one = {}
    chaos = 0
    thresh = 0.01
    degrade_amount = 0.05
    improve_amount = 0.05

    # NOTE: This is the borg singleton pattern - __we_are_all_one
    def __new__(cls, *args, **kwargs):
        """
        Create the shared instance
        """
        obj = super(ReceptionStatus, cls).__new__(cls, *args, **kwargs)
        obj.__dict__ = cls.__we_are_all_one
        return obj

    def __init__(self):
        """
        Initialize the instance
        """
        pass

    def is_perfect(self):
        """
        Is perfect
        """
        return self.chaos == 0.0

    def is_degraded(self):
        """
        Is degraded
        """
        return self.chaos > self.thresh

    def is_fully_degraded(self):
        """
        Is fully degraded
        """
        return self.chaos == 1.0

    def degrade(self, override=0):
        """
        Degrade
        """
        if override == 0:
            self.chaos += self.degrade_amount
        else:
            self.chaos += override

        if self.chaos > 1.0:
            self.chaos = 1.0

    def improve(self, override=0):
        """
        Improve
        """
        if override == 0:
            self.chaos -= self.improve_amount
        else:
            self.chaos -= override

        if self.chaos < self.thresh:
            self.chaos = 0.0

    def filter(self):
        """
        Filter
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
    ScrambledVideoFilter
    """

    def __init__(self):
        """
        Initialize the instance
        """
        pass

    def update_filter(self):
        """
        Update filter
        """
        return ''


class HLScrambledVideoFilter(ScrambledVideoFilter):
    """
    HLScrambledVideoFilter
    """

    def __init__(self):
        """
        Initialize the instance
        """
        self.chaos = 50
        self.thrust = 20

    def update_filter(self):
        """
        Update filter
        """

        if random.random() > .95:
            self.chaos = random.randint(40, 70)
        if random.random() > .9:
            self.chaos = random.randint(10, 30)
        return "lavfi=[geq='if(mod(floor(Y/4),2),p(X,Y+{0}*sin(2*PI*X/{1})),p(X,Y))']".format(
            self.thrust, self.chaos)


class DiagonalScrambledVideoFilter(ScrambledVideoFilter):
    """
    DiagonalScrambledVideoFilter
    """

    def __init__(self):
        """
        Initialize the instance
        """
        self.chaos = 50
        self.thrust = 20

    def update_filter(self):
        """
        Update filter
        """

        if random.random() > .95:
            self.chaos = random.randint(5, 15)
        if random.random() > .9:
            self.chaos = random.randint(20, 40)
        return "lavfi=[geq='p(X+{0}*sin(2*PI*Y/{1}),Y)']".format(self.chaos, self.thrust)


class ColorInvertedScrambledVideoFilter(ScrambledVideoFilter):
    """
    ColorInvertedScrambledVideoFilter
    """

    def __init__(self):
        """
        Initialize the instance
        """
        self.chaos = 50
        self.thrust = 20

    def update_filter(self):
        """
        Update filter
        """

        if random.random() > .95:
            self.chaos = random.randint(8, 12)

        return "lavfi=[geq='if(mod(floor(Y/{}),2),255-p(X,Y),p(X,Y))']".format(self.chaos)


class ChunkyScrambledVideoFilter(ScrambledVideoFilter):
    """
    ChunkyScrambledVideoFilter
    """

    def __init__(self):
        """
        Initialize the instance
        """
        pass

    def update_filter(self):
        """
        Update filter
        """
        return "lavfi=[scale=320:240,split[base][aux];[aux]geq=r='p(X+floor((random(1000+floor(N*0.05)+floor(Y/16))-0.5)*W*0.4),Y)':g='p(X+floor((random(2000+floor(N*0.05)+floor(Y/16))-0.5)*W*0.4),Y)':b='p(X+floor((random(3000+floor(N*0.05)+floor(Y/16))-0.5)*W*0.4),Y)'[warped];[base][warped]overlay,scale=640:480]"
