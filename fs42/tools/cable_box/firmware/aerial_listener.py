#!/usr/bin/env python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Manage aerial listener
"""
# this runs on the pico component - not the pi

import time

import board
import busio
import neopixel
import digitalio
import adafruit_ssd1306
from rainbowio import colorwheel

# Keep the Pico program self-contained for deployment as code.py.
RED = (255, 0, 0)
YELLOW = (255, 150, 0)
YELLOW2 = (225, 120, 0)
GREEN = (0, 255, 0)
CYAN = (0, 255, 255)
BLUE = (0, 0, 255)
PURPLE = (180, 0, 255)

i2cOLED = busio.I2C(board.GP19, board.GP18)
oled = adafruit_ssd1306.SSD1306_I2C(128, 32, i2cOLED)

oled.fill(0)
oled.text('Hello', 0, 0, 1)
oled.text('World', 0, 10, 1)
oled.show()

led = digitalio.DigitalInOut(board.LED)

led.direction = digitalio.Direction.OUTPUT
uart = busio.UART(tx=board.GP0, rx=board.GP1, baudrate=9600)

chan_btn = digitalio.DigitalInOut(board.GP14)
chan_btn.direction = digitalio.Direction.INPUT
chan_btn.pull = digitalio.Pull.UP

exit_btn = digitalio.DigitalInOut(board.GP2)
exit_btn.direction = digitalio.Direction.INPUT
exit_btn.pull = digitalio.Pull.UP

halt_btn = digitalio.DigitalInOut(board.GP27)
halt_btn.direction = digitalio.Direction.INPUT
halt_btn.pull = digitalio.Pull.UP

pixel_pin = board.GP16
num_pixels = 8

pixels = neopixel.NeoPixel(pixel_pin, num_pixels, brightness=0.3, auto_write=False)


def color_chase(color, wait):
    """
    Color chase
    """
    for i in range(num_pixels):
        pixels[i] = color
        time.sleep(wait)
        pixels.show()
    time.sleep(0.5)


def rainbow_cycle(wait):
    """
    Rainbow cycle
    """
    for j in range(255):
        for i in range(num_pixels):
            rc_index = (i * 256 // num_pixels) + j
            pixels[i] = colorwheel(rc_index & 255)
        pixels.show()
        time.sleep(wait)


def show_waiting():
    """
    Show waiting
    """
    oled.fill(0)
    oled.text('Waiting...', 0, 10, 1)
    oled.show()


def show_command(cmd):
    """
    Show command
    """
    oled.fill(0)
    oled.text('CMD: {}'.format(cmd), 0, 0, 1)
    oled.show()


def show_ambient():
    """
    Show ambient
    """
    pixels.fill(YELLOW)
    pixels.show()


show_waiting()
show_ambient()

while True:
    # led.value = not led.value
    if not chan_btn.value:
        uart.write(b"change\n")
        print('Pressed')
        oled.fill(0)
        oled.text('Command: change', 0, 0, 1)
        oled.show()
        rainbow_cycle(0.015)
        rainbow_cycle(0.015)

        show_waiting()
        show_ambient()

    if not exit_btn.value:
        uart.write(b"exit\n")
        show_command('exit')
        pixels.fill(CYAN)
        pixels.show()
        time.sleep(5)
        show_waiting()
        show_ambient()

    if not halt_btn.value:
        uart.write(b"halt\n")
        show_command('halt')
        pixels.fill(RED)
        pixels.show()
        time.sleep(5)
        show_waiting()
        show_ambient()
