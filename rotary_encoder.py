#!/usr/bin/env python3

""" The daemon responsible for changing the volume in response to a turn or press
    of the volume knob.
    The volume knob is a rotary encoder. It turns infinitely in either direction.
    Turning it to the right will increase the volume; turning it to the left will
    decrease the volume. The knob can also be pressed like a button in order to
    turn muting on or off.
    The knob uses two GPIO pins and we need some extra logic to decode it. The
    button we can just treat like an ordinary button. Rather than poll
    constantly, we use threads and interrupts to listen on all three pins in one
    script.
"""

import subprocess
import sys
import threading
import signal
import logging
import queue
from RPi import GPIO

#===Settings====#

#[Potentiometer]
# The two pins that the encoder uses (BCM numbering).
PM_GPIO_A = 10
PM_GPIO_B = 11
# The pin that the knob's button is hooked up to. If you have no button, set
# this to None.
PM_GPIO_BUTTON = 12

#[Volume]
# The minimum and maximum volumes, as percentages.
#
# The default max is less than 100 to prevent distortion. The default min is
# greater than zero because if your system is like mine, sound gets
# completely inaudible _long_ before 0%. If you've got a hardware amp or
# serious speakers or something, your results will vary.
VOLUME_MIN = 60
VOLUME_MAX = 96

# The amount you want one click of the knob to increase or decrease the
# volume. I don't think that non-integer values work here, but you're welcome
# to try.
VOLUME_INCREMENT = 1


# Control Id for amixer command. It depends of your linux configuration
VOLUME_MIXER_CONTROL_ID = "Master"

#[Debug]
DEBUG = False

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(message)s')

class RotaryEncoder(object):
    """ A class to decode mechanical rotary encoder pulses.
        Ported to RPi.GPIO from the pigpio sample here:
        http://abyz.co.uk/rpi/pigpio/examples.html
    """
    def __init__(self, gpioA, gpioB, callback=None, gpioButton=None, buttonCallback=None):
        """ Instantiate the class. Takes three arguments: the two pin numbers to
            which the rotary encoder is connected, plus a callback to run when the
            switch is turned.
            The callback receives one argument: a `delta` that will be either 1 or -1.
            One of them means that the dial is being turned to the right; the other
            means that the dial is being turned to the left. I'll be damned if I know
            yet which one is which.
        """

        self._gpio_a = gpioA
        self._gpio_b = gpioB
        self._lev_a = 0
        self._lev_b = 0
        self._callback = callback
        self._last_gpio = None

        self._gpio_button = gpioButton
        self._button_callback = buttonCallback

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self._gpio_a, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(self._gpio_b, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        GPIO.add_event_detect(self._gpio_a, GPIO.BOTH, self._gpio_input_rotation_callback)
        GPIO.add_event_detect(self._gpio_b, GPIO.BOTH, self._gpio_input_rotation_callback)

        if self._gpio_button:
            GPIO.setup(self._gpio_button, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.add_event_detect(self._gpio_button, GPIO.FALLING,
                                  self._gpio_input_button_callback, bouncetime=500)

    def __del__(self):
        GPIO.remove_event_detect(self._gpio_a)
        GPIO.remove_event_detect(self._gpio_b)
        if self._gpio_button:
            GPIO.remove_event_detect(self._gpio_button)
        GPIO.cleanup()

    def _gpio_input_button_callback(self, channel):
        self._button_callback(GPIO.input(channel))

    def _gpio_input_rotation_callback(self, channel):
        level = GPIO.input(channel)
        if channel == self._gpio_a:
            self._lev_a = level
        else:
            self._lev_b = level

        # Debounce
        if channel == self._last_gpio:
            return

        # When both inputs are at 1, we'll fire a callback. If A was the most
        # recent pin set high, it'll be forward, and if B was the most recent pin
        # set high, it'll be reverse.
        self._last_gpio = channel
        if channel == self._gpio_a and level == 1:
            if self._lev_b == 1:
                self._callback(1)
        elif channel == self._gpio_b and level == 1:
            if self._lev_a == 1:
                self._callback(-1)


class Volume(object):
    """ A wrapper API for interacting with the volume settings on the RPi. """

    def __init__(self):
        self._min = VOLUME_MIN
        self._max = VOLUME_MAX
        self._increment = VOLUME_INCREMENT
        self._last_volume = VOLUME_MIN
        self._volume = VOLUME_MIN
        self._is_muted = False
        self._sync()

    def up(self):
        """ Increases the volume by one increment. """
        return self._set_volume(self._volume + self._increment)

    def down(self):
        """ Decreases the volume by one increment. """
        return self._set_volume(self._volume - self._increment)

    def toggle(self):
        """ Toggles muting between on and off. """
        if self._is_muted:
            cmd = "set '{}' unmute".format(VOLUME_MIXER_CONTROL_ID)
        else:
            # We're about to mute ourselves, so we should remember the last volume
            # value we had because we'll want to restore it later.
            self._last_volume = self._volume
            cmd = "set '{}' mute".format(VOLUME_MIXER_CONTROL_ID)
        self._sync(self._amixer(cmd))
        if not self._is_muted:
            # If we just unmuted ourselves, we should restore whatever volume we
            # had previously.
            self._set_volume(self._last_volume)
        return self._is_muted

    def get_volume(self):
        """ Volume accessor """
        return self._volume

    def _set_volume(self, val):
        """ Sets volume to a specific value. """
        self._volume = self._constrain(val)
        self._sync(self._amixer("set '{}' unmute {}%".format(VOLUME_MIXER_CONTROL_ID, val)))
        return self._volume

    # Ensures the volume value is between our minimum and maximum.
    def _constrain(self, val):
        if val < self._min:
            return self._min
        if val > self._max:
            return self._max
        return val

    def _amixer(self, cmd):
        """ Execute bash command to set up sound level on linux environement.
            Return output of command
        """
        process = subprocess.Popen("amixer {}".format(cmd), shell=True, stdout=subprocess.PIPE)
        code = process.wait()
        if code != 0:
            #Error : unable to setup volume level / mute - unmute
            sys.exit(0)
        return process.stdout

    def _sync(self, output=None):
        """ Read the output of `amixer` to get the system volume and mute state.
            This is designed not to do much work because it'll get called with every
            click of the knob in either direction, which is why we're doing simple
            string scanning and not regular expressions.
        """
        if output is None:
            output = self._amixer("get '{}'".format(VOLUME_MIXER_CONTROL_ID))
        lines = output.readlines()
        #if STACK_TRACE:
            #strings = [line.decode('utf8') for line in lines]
            #print "OUTPUT:"
            #print "".join(strings)
        last = lines[-1].decode('utf-8')

        # The last line of output will have two values in square brackets. The
        # first will be the volume (e.g., "[95%]") and the second will be the
        # mute state ("[off]" or "[on]").
        index_1 = last.rindex('[') + 1
        index_2 = last.rindex(']')

        self.is_muted = last[index_1:index_2] == 'off'

        index_1 = last.index('[') + 1
        index_2 = last.index('%')
        # In between these two will be the percentage value.
        pct = last[index_1:index_2]

        self._volume = int(pct)

class EventWrapper(object):
    """ This class encapsulate event, fire by knob action, and put volume delta into FIFO queue.
        This is necessary to ensure than every action is treat in order by main thread
    """
    def __init__(self):
        self._volume = Volume()
        self._queue = queue.Queue()
        self._event = threading.Event()
        self._encoder = RotaryEncoder(PM_GPIO_A, PM_GPIO_B, callback=self._on_turn,
                                      gpioButton=PM_GPIO_BUTTON,
                                      buttonCallback=self._on_press_toggle)

        signal.signal(signal.SIGINT, self._on_exit)
        logging.debug("Volume knob using pins %s (A) and %s (B)", PM_GPIO_A, PM_GPIO_B)
        if PM_GPIO_BUTTON != None:
            logging.debug("Volume mute button using pin %s", PM_GPIO_BUTTON)
        logging.debug("Initial volume: %s", self._volume.get_volume())

    def _on_press_toggle(self):
        self._volume.toggle()
        logging.debug("Toggled mute to: %s", self._volume.is_muted)
        self._event.set()

    def _on_turn(self, delta):
        self._queue.put(delta)
        self._event.set()

    def _on_exit(self):
        logging.debug("Exiting...")
        self._encoder.__del__()
        sys.exit(0)

    def wait_event(self, seconde):
        """ This method stop main thread until event fires """
        self._event.wait(seconde)

    def consume_queue(self):
        """ This method loop on queue and increase or decrease volume according to delta value """
        while not self._queue.empty():
            if self._queue.get() == 1:
                self._volume.up()
                logging.debug("Increase volume")
            else:
                logging.debug("Decrease volume")
                self._volume.down()

    def clear_event(self):
        """ Flush Events once queue is empty """
        self._event.clear()

if __name__ == "__main__":
    WRAPPER = EventWrapper()
    while True:
        # This is the best way I could come up with to ensure that this script
        # runs indefinitely without wasting CPU by polling. The main thread will
        # block quietly while waiting for the event to get flagged. When the knob
        # is turned we're able to respond immediately, but when it's not being
        # turned we're not looping at all.
        #
        # The 1200-second (20 minute) timeout is a hack; for some reason, if I
        # don't specify a timeout, I'm unable to get the SIGINT handler above to
        # work properly. But if there is a timeout set, even if it's a very long
        # timeout, then Ctrl-C works as intended. No idea why.
        WRAPPER.wait_event(1200)
        WRAPPER.consume_queue()
        WRAPPER.clear_event()
