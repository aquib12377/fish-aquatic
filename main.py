"""
Robotic fish main loop and single entry point for the whole robot: swims a
travelling-wave gait, steers away from obstacles detected by the AJ-SR04M,
runs the camera in either SD-card recording or MJPEG live-stream mode, and
serves the web dashboard (web_dashboard.py) on 0.0.0.0 so any device on the
LAN can watch the live distance reading and flip the camera mode.

Run the test_servos.py / test_ultrasonic.py / test_camera.py scripts first
to confirm each subsystem individually, THEN run this:

    source ~/fishenv/bin/activate
    python3 main.py

Then browse to http://<pi-ip>:5000/ from any device on the same network.
See README.md for the dashboard's "no authentication" caveat and TESTING.md
for how to check each piece is actually working.
"""
import time
import threading

from servo_controller import FishServoController
from ultrasonic_sensor import ObstacleSensor
from camera_module import FishCamera, prune_old_recordings
from web_dashboard import create_app

AVOID_THRESHOLD_CM = 25
VIDEO_SEGMENT_SECONDS = 300    # 5 min per file -- bounds file size & corruption risk
MAX_SEGMENTS_KEPT = 24         # ~2 hours of footage at the default segment length
                                # -- tune to your SD card's free space, see README
DASHBOARD_HOST = "0.0.0.0"
DASHBOARD_PORT = 5000

latest_distance_cm = None
camera_mode = "record"     # "record" (SD card, today's default) or "stream" (live MJPEG)
latest_jpeg_frame = None
_lock = threading.Lock()


def get_distance():
    with _lock:
        return latest_distance_cm


def get_camera_mode():
    with _lock:
        return camera_mode


def set_camera_mode(mode):
    global camera_mode
    with _lock:
        camera_mode = mode


def get_jpeg_frame():
    with _lock:
        return latest_jpeg_frame


def sensor_loop(obs):
    global latest_distance_cm
    while True:
        d = obs.distance_cm()
        with _lock:
            latest_distance_cm = d
        time.sleep(0.1)


def swim_loop(fish):
    start = time.time()
    while True:
        d = get_distance()
        turn_bias = 0.0
        if d is not None and d < AVOID_THRESHOLD_CM:
            turn_bias = 1.0  # turn away when something is close ahead
        fish.swim_step(time.time() - start, turn_bias=turn_bias)
        time.sleep(0.02)


def camera_loop(cam):
    """
    Runs the camera in whichever mode the dashboard toggle last selected.
    Only one mode is ever active on the camera at once -- switching modes
    cleanly stops the previous one before starting the next.
    """
    global latest_jpeg_frame
    active_mode = None
    recording_deadline = 0

    while True:
        mode = get_camera_mode()

        if mode != active_mode:
            if active_mode == "record":
                cam.stop_recording()
            elif active_mode == "stream":
                cam.stop_stream()

            if mode == "record":
                path = cam.start_recording_to_file()
                print(f"recording -> {path}")
                recording_deadline = time.time() + VIDEO_SEGMENT_SECONDS
            elif mode == "stream":
                cam.start_stream()
                print("live stream started")

            active_mode = mode

        try:
            if mode == "record":
                if time.time() >= recording_deadline:
                    cam.stop_recording()
                    prune_old_recordings(MAX_SEGMENTS_KEPT)
                    path = cam.start_recording_to_file()
                    print(f"recording -> {path}")
                    recording_deadline = time.time() + VIDEO_SEGMENT_SECONDS
                time.sleep(0.5)
            elif mode == "stream":
                frame = cam.get_jpeg_frame()
                with _lock:
                    latest_jpeg_frame = frame
            else:
                time.sleep(0.5)
        except Exception as exc:
            print(f"camera loop error ({mode}): {exc}")
            active_mode = None  # force a clean mode restart next iteration
            time.sleep(2)


def main():
    fish = FishServoController()
    obs = ObstacleSensor()
    cam = FishCamera()

    threading.Thread(target=sensor_loop, args=(obs,), daemon=True).start()
    threading.Thread(target=swim_loop, args=(fish,), daemon=True).start()
    threading.Thread(target=camera_loop, args=(cam,), daemon=True).start()

    app = create_app(get_distance, get_camera_mode, set_camera_mode, get_jpeg_frame)
    try:
        # threaded=True: lets the long-lived MJPEG stream connection and the
        # short distance-polling requests be served concurrently -- see
        # README's caveat about resource limits on a single ARM11 core.
        app.run(host=DASHBOARD_HOST, port=DASHBOARD_PORT, threaded=True)
    except KeyboardInterrupt:
        pass
    finally:
        fish.release()
        obs.close()
        cam.close()  # also stops whichever camera mode was active


if __name__ == "__main__":
    main()
