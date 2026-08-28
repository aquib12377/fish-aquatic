"""
AJ-SR04M ultrasonic distance sensor, Mode 1 (trigger/echo, HC-SR04-compatible).

Wiring:
    AJ-SR04M VCC  -> external 5V supply (NOT the Pi's 5V pin -- see README)
    AJ-SR04M GND  -> common ground
    AJ-SR04M TRIG -> Pi GPIO23 (direct connection is fine, Pi drives it)
    AJ-SR04M ECHO -> voltage divider (e.g. 1k series + 2k to GND) -> Pi GPIO24
                     ECHO idles/pulses at ~5V and WILL damage a 3.3V GPIO
                     input if wired directly.

IMPORTANT (aquatic use): this sensor is designed for non-contact distance
measurement THROUGH AIR (e.g. a tank-level sensor mounted above the water,
pointed down at the surface). Its timing math assumes the speed of sound in
air (~343 m/s). It will NOT work correctly, and is not intended to work, as
sonar while its transducer face is actually submerged -- see README.md.
"""
from gpiozero import DistanceSensor

TRIG_PIN = 23
ECHO_PIN = 24
MAX_RANGE_M = 4.0     # AJ-SR04M is commonly rated ~2 cm - 4.5 m in air
QUEUE_LEN = 5          # smooths noisy readings


class ObstacleSensor:
    def __init__(self):
        self.sensor = DistanceSensor(
            echo=ECHO_PIN,
            trigger=TRIG_PIN,
            max_distance=MAX_RANGE_M,
            queue_len=QUEUE_LEN,
        )

    def distance_cm(self):
        return self.sensor.distance * 100

    def close(self):
        self.sensor.close()


# This module is a library -- run test_ultrasonic.py to bring up and test
# the hardware, or main.py to run the full robot.
