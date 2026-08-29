"""
Servo controller for the 4-joint robotic fish spine.
Drives 4x EMAX ES08MA II analog servos through a PCA9685
16-channel PWM driver over I2C.

Wiring (see README.md for full pin map):
    Pi 3.3V  -> PCA9685 VCC
    Pi GPIO2 (SDA) -> PCA9685 SDA
    Pi GPIO3 (SCL) -> PCA9685 SCL
    Pi GND   -> PCA9685 GND (logic) AND servo supply GND (common ground)
    External 5-6V supply -> PCA9685 V+ terminal (servo power, NOT from the Pi)
    Servos   -> PCA9685 channels 0, 1, 2, 3
"""
import math
import board
import busio
from adafruit_pca9685 import PCA9685
from adafruit_motor import servo

# ---- Configuration ----
PCA9685_ADDRESS = 0x40
PWM_FREQUENCY_HZ = 50           # standard analog servo refresh rate
SERVO_CHANNELS = [0, 1, 2, 3]   # head -> tail joint order
SERVO_MIN_PULSE = 600           # µs -- calibrate per servo, see README
SERVO_MAX_PULSE = 2400           # µs -- calibrate per servo, see README
CENTER_ANGLE = 90
SWING_DEGREES = 35               # amplitude of each joint's swing
WAVE_SPEED_HZ = 0.9              # tail-beat frequency
PHASE_LAG_DEG = 60               # phase offset per joint -> travelling wave


class FishServoController:
    def __init__(self):
        i2c = busio.I2C(board.SCL, board.SDA)
        self.pca = PCA9685(i2c, address=PCA9685_ADDRESS)
        self.pca.frequency = PWM_FREQUENCY_HZ
        self.servos = [
            servo.Servo(
                self.pca.channels[ch],
                min_pulse=SERVO_MIN_PULSE,
                max_pulse=SERVO_MAX_PULSE,
            )
            for ch in SERVO_CHANNELS
        ]

    def set_angle(self, joint_index, angle):
        angle = max(0, min(180, angle))
        self.servos[joint_index].angle = angle

    def center_all(self):
        for s in self.servos:
            s.angle = CENTER_ANGLE

    def swim_step(self, t, turn_bias=0.0):
        """
        Compute one instant of a travelling-wave swim gait, head -> tail.

        turn_bias: -1.0 (hard left) .. 0.0 (straight) .. 1.0 (hard right)
        shifts each joint's mean angle to steer while still swimming.
        """
        for i, s in enumerate(self.servos):
            phase = math.radians(i * PHASE_LAG_DEG)
            wave = SWING_DEGREES * math.sin(2 * math.pi * WAVE_SPEED_HZ * t + phase)
            steer = turn_bias * SWING_DEGREES * 0.6 * (i / len(self.servos))
            angle = CENTER_ANGLE + wave + steer
            s.angle = max(0, min(180, angle))

    def idle_all(self):
        """
        Stop sending pulses so servos go limp, same as release() -- but
        without deinitializing the PCA9685, so swim_step()/center_all() can
        resume afterward without recreating the controller. Used by the web
        dashboard's bot on/off toggle to pause the gait; release() remains
        the one-way shutdown call for program exit.
        """
        for s in self.servos:
            s.angle = None

    def release(self):
        """Stop sending pulses so servos don't hold torque / buzz when idle."""
        for s in self.servos:
            s.angle = None
        self.pca.deinit()


# This module is a library -- run test_servos.py to bring up and test the
# hardware, or main.py to run the full robot.
