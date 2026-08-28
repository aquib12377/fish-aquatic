"""
Test Servos -- standalone bring-up test for the 4 ES08MA II joints.

Run this BEFORE main.py to confirm each servo is wired to the correct
PCA9685 channel, moves smoothly, and doesn't bind at the ends of its travel.

    source ~/fishenv/bin/activate
    python3 test_servos.py
"""
import time
from servo_controller import FishServoController, SERVO_CHANNELS, CENTER_ANGLE

STEP_DELAY_S = 0.02
HOLD_DELAY_S = 0.5
SWEEP_LOW = 45
SWEEP_HIGH = 135


def sweep_one(fish, joint_index):
    """Move a single joint center -> low -> high -> center; others stay put."""
    print(f"  channel {SERVO_CHANNELS[joint_index]}: sweeping {SWEEP_LOW}-{SWEEP_HIGH} deg")
    for angle in range(CENTER_ANGLE, SWEEP_LOW, -1):
        fish.set_angle(joint_index, angle)
        time.sleep(STEP_DELAY_S)
    time.sleep(HOLD_DELAY_S)
    for angle in range(SWEEP_LOW, SWEEP_HIGH + 1):
        fish.set_angle(joint_index, angle)
        time.sleep(STEP_DELAY_S)
    time.sleep(HOLD_DELAY_S)
    for angle in range(SWEEP_HIGH, CENTER_ANGLE - 1, -1):
        fish.set_angle(joint_index, angle)
        time.sleep(STEP_DELAY_S)


def main():
    print("Connecting to PCA9685...")
    fish = FishServoController()

    try:
        print("Centering all 4 joints...")
        fish.center_all()
        time.sleep(1)

        print("Testing each joint individually (head -> tail). Watch for:")
        print("  - the correct joint moving on the correct channel")
        print("  - smooth motion with no grinding/stalling at the endpoints")
        for i in range(len(SERVO_CHANNELS)):
            sweep_one(fish, i)
            fish.set_angle(i, CENTER_ANGLE)
            time.sleep(0.3)

        print("Individual joints OK. Running 5s of the swim gait (all 4 together)...")
        start = time.time()
        while time.time() - start < 5:
            fish.swim_step(time.time() - start)
            time.sleep(0.02)

        print("Servo test complete.")
    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        fish.release()


if __name__ == "__main__":
    main()
