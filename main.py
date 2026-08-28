"""
Robotic fish main loop: swims a travelling-wave gait, steers away from
obstacles detected by the AJ-SR04M, and continuously records video to the
SD card in fixed-length segments (so no single file grows unbounded and a
power loss mid-recording only risks the current segment).

Run the test_servos.py / test_ultrasonic.py / test_camera.py scripts first
to confirm each subsystem individually, THEN run this:

    source ~/fishenv/bin/activate
    python3 main.py
"""
import time
import threading

from servo_controller import FishServoController
from ultrasonic_sensor import ObstacleSensor
from camera_module import FishCamera, prune_old_recordings

AVOID_THRESHOLD_CM = 25
VIDEO_SEGMENT_SECONDS = 300    # 5 min per file -- bounds file size & corruption risk
MAX_SEGMENTS_KEPT = 24         # ~2 hours of footage at the default segment length
                                # -- tune to your SD card's free space, see README

latest_distance_cm = None
_lock = threading.Lock()


def sensor_loop(obs):
    global latest_distance_cm
    while True:
        d = obs.distance_cm()
        with _lock:
            latest_distance_cm = d
        time.sleep(0.1)


def camera_loop(cam):
    while True:
        try:
            path = cam.start_recording_to_file()
            print(f"recording -> {path}")
            time.sleep(VIDEO_SEGMENT_SECONDS)
            cam.stop_recording()
            prune_old_recordings(MAX_SEGMENTS_KEPT)
        except Exception as exc:
            print(f"camera recording failed: {exc}")
            time.sleep(2)


def main():
    fish = FishServoController()
    obs = ObstacleSensor()
    cam = FishCamera()

    threading.Thread(target=sensor_loop, args=(obs,), daemon=True).start()
    threading.Thread(target=camera_loop, args=(cam,), daemon=True).start()

    start = time.time()
    try:
        while True:
            with _lock:
                d = latest_distance_cm
            turn_bias = 0.0
            if d is not None and d < AVOID_THRESHOLD_CM:
                turn_bias = 1.0  # turn away when something is close ahead
            fish.swim_step(time.time() - start, turn_bias=turn_bias)
            time.sleep(0.02)
    except KeyboardInterrupt:
        pass
    finally:
        fish.release()
        obs.close()
        cam.close()  # also stops and closes out the in-progress video segment


if __name__ == "__main__":
    main()
