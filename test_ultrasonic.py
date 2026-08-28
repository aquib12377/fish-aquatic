"""
Test Ultrasonic -- standalone bring-up test for the AJ-SR04M.

Run this BEFORE main.py to confirm the sensor is wired correctly (including
the ECHO voltage divider) and returns sane, changing readings.

    source ~/fishenv/bin/activate
    python3 test_ultrasonic.py
"""
import time
from ultrasonic_sensor import ObstacleSensor

DURATION_S = 15
SAMPLE_INTERVAL_S = 0.25


def main():
    print(f"Reading distance for {DURATION_S}s (Ctrl+C to stop early).")
    print("Wave a flat object in front of the sensor and confirm the number changes.\n")
    obs = ObstacleSensor()
    readings = []
    start = time.time()
    try:
        while time.time() - start < DURATION_S:
            d = obs.distance_cm()
            readings.append(d)
            print(f"  {d:6.1f} cm")
            time.sleep(SAMPLE_INTERVAL_S)
    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        obs.close()

    if readings:
        print(
            f"\nmin={min(readings):.1f} cm  max={max(readings):.1f} cm  "
            f"avg={sum(readings) / len(readings):.1f} cm  samples={len(readings)}"
        )
        print(
            "If every reading is stuck at 0 or at the sensor's max range, check "
            "the TRIG/ECHO wiring and the ECHO voltage divider before proceeding."
        )
    else:
        print("No readings captured.")


if __name__ == "__main__":
    main()
