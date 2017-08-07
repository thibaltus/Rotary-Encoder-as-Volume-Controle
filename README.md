# Rotary-Encoder-as-Volume-Controle

On my Raspberry Pi machine I wanted a hardware volume knob. The speakers I got for my cabinet are great, but don't have their own hardware volume knob. So with a bunch of googling and trial and error, I figured out what I need to pull this off: a rotary encoder and a daemon that listens for the signals it sends.

## Rotary encoder

A rotary encoder is like the standard potentiometer (i.e., analog volume knob) we all know, except (a) you can keep turning it in either direction for as long as you want, and thus (b) it talks to the RPi differently than a potentiometer would.

I picked up [this one](https://www.adafruit.com/products/377) from Adafruit, but there are plenty others available. This rotary encoder also lets you push the knob in and treats that like a button press, so I figured that would be useful for toggling mute on and off.

So we've got 5 wires to hook up: three for the knob part (A, B, and ground), and two for the button part (common and ground). Here's how I hooked them up ([reference](https://ms-iot.github.io/content/images/PinMappings/RP2_Pinout.png)):

| Description   | BCM #                       | Board # |
|---------------|-----------------------------|---------|
| knob A        | GPIO 26                     | 37      |
| knob B        | GPIO 19                     | 35      |
| knob ground   | ground pin below GPIO 26    | 39      |
| button common | GPIO 13                     | 33      |
| button ground | ground pin opposite GPIO 13 | 34      |

You can use whichever pins you want; just update the script if you change them.

## Volume daemon

Since the GPIO pins are just for arbitrary signals, you need a script on the Pi that knows what to do with them. The builtin GPIO library for the Pi will do nicely for this.
 
You'll see the script below, but here's how it works: it listens on the specified pins, and when the knob is turned one way or another, it uses the states of the A and B pins to figure out whether the knob was turned to the left or to the right. That way it knows whether to increase or decrease the system volume in response, which it does with the command-line program `amixer`.

First, make sure `amixer` is present and install it if it isn’t.

```sh
which amixer || sudo apt-get install alsa-utils
```

(If you’re not using the default analog audio output, consult @thijstriemstra’s comment below for some additional steps that you may or may not need to do.)

Create a `bin` directory in your `pi` folder if it doesn't exist already, then drop the script below into it.

```
mkdir ~/bin
```

If it's not there yet, I'd also put `/home/pi/bin` somewhere in your `PATH`:

```
echo $PATH
# don't see "/home/pi/bin" there? then run...
echo "export PATH=$HOME/bin:$PATH" >> ~/.bashrc
# ...and restart your shell
```

Then drop the script into the `/home/pi/bin` folder:

```
nano ~/bin/monitor-volume # (or however you do it)
chmod +x ~/bin/monitor-volume
```

You can run this script in the foreground just to test it out. Edit the script and temporarily change `DEBUG` to `True` so that you can see what's going on, then simply run it with `monitor-volume`. When you turn or press the knob, the script should report what it's doing. (Make sure that the volume _increases_ rather than _decreases_ when you turn it to the right, and if it doesn't, swap your A and B pins, or just swap their numbers in the script.)

You should also play around with the constants defined at the top of the script. Naturally, if you picked other pins, you'll want to tell the script which GPIO pins to use. If your rotary encoder doesn't act like a button, or if you didn't hook up the button and don't care about it, you can set `GPIO_BUTTON` to `None`. But you may also want to change the minimum and maximum volumes (they're percentages, so they should be between 1 and 100) and the increment (how many percentage points the volume increases/decreases with each "click" of the knob).

If it's working the way you want, you can proceed to the next step: running `monitor-volume` automatically in the background whenever your Pi starts.

## Creating a systemd service

_NOTE: If you're on a version of Raspbian before Jessie, these instructions won't work for you. Hopefully someone can pipe up with a version of this for `init.d` in the comments._

`systemd` is the new way of managing startup daemons in Raspbian Jessie. Because it's new, there's not much RPi-specific documentation on it, and to find out how to use it you have to sift through a bunch of Google results from people who hate `systemd` and wish it didn't exist. After much trial and error, here's what worked for me:

```
nano ~/monitor-volume.service
# paste in the contents of monitor-volume.service, save/exit nano
chmod +x ~/monitor-volume.service
sudo mv ~/monitor-volume.service /etc/systemd/system
sudo systemctl enable monitor-volume
sudo systemctl start monitor-volume
```

If that worked right, then you just told Raspbian to start up that script in the background on every boot (`enable`), and also to start it right now (`start`). At this point, and on every boot after this, your volume knob should Just Work.

##  FAQ

**This didn't work!**

I got this working on an RPi3 running RetroPie 3.x, so all I can say is “works on my machine.” Some things to try:

* You might not have Python 3; if `which python3` turns up nothing, try this:

  ```
  sudo apt-get install python3 python3-rpi.gpio
  ```
* I've heard that in earlier versions of Raspbian, the `pi` user isn't automatically allowed to access the GPIO pins, so you need to run scripts like this as root.  If you're running into permissions errors when you try to run the script from your shell, then that's your problem, most likely. There's no particular reason why you _shouldn't_ run this script as root, except on the general principle that you shouldn't really trust code that you didn't write. Make good choices and have backups.
* I might have made a typo in the gist. Wouldn't be the first time.

If you run into trouble, leave a comment and the internet can help you figure it out.
