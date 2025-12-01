# requires installation of:
# 	sudo pip3 install rpi_ws281x adafruit-circuitpython-neopixel
#	sudo python3 -m pip install --force-reinstall adafruit-blinka

# to implement when gesture is recognized:
#	from led_feedback import led_feedback
#	led_feedback()

import time
import board
import neopixel

LED_PIN = board.D21      # GPIO21 (physical pin 40)
NUM_LEDS = 60
BRIGHTNESS = 0.5         # 0–1

pixels = neopixel.NeoPixel(
    LED_PIN,
    NUM_LEDS,
    brightness=BRIGHTNESS,
    auto_write=True,
    pixel_order=neopixel.GRB
)

def flash_green():
    pixels.fill((0, 255, 0))
    time.sleep(0.3)
    pixels.fill((0, 0, 0))

if __name__ == "__main__":
    print("Flashing once")
    flash_green()

