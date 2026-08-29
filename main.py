"""
Robotic fish main loop and single entry point for the whole robot: swims a
travelling-wave gait, steers away from obstacles detected by the AJ-SR04M,
runs the camera in either SD-card recording or MJPEG live-stream mode, and
serves the web dashboard (web_dashboard.py) on 0.0.0.0 so any device on the
LAN can watch the live distance reading, flip the camera mode, pause/resume
the swim gait, and run a quick self-test of each subsystem.

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
from collections import deque

from servo_controller import FishServoController, SERVO_CHANNELS, CENTER_ANGLE
from ultrasonic_sensor import ObstacleSensor
from camera_module import FishCamera, prune_old_recordings, CAPTURES_DIR
from web_dashboard import create_app

AVOID_THRESHOLD_CM = 25
VIDEO_SEGMENT_SECONDS = 300    # 5 min per file -- bounds file size & corruption risk
MAX_SEGMENTS_KEPT = 24         # ~2 hours of footage at the default segment length
                                # -- tune to your SD card's free space, see README
DASHBOARD_HOST = "0.0.0.0"
DASHBOARD_PORT = 5000

DISTANCE_HISTORY_LEN = 50       # ~5s of samples at the sensor loop's 0.1s interval
SERVO_TEST_SWEEP_LOW = 60
SERVO_TEST_SWEEP_HIGH = 120
SERVO_TEST_STEP_DELAY_S = 0.02

# ---- Shared state, all guarded by _lock -- same daemon-thread-plus-lock
# pattern as the original swim/sensor loop; one lock rather than several
# since contention is a non-issue on a single-core GIL'd interpreter. ----
latest_distance_cm = None
distance_history = deque(maxlen=DISTANCE_HISTORY_LEN)   # [(timestamp, distance_cm), ...]
camera_mode = "record"     # "record" (SD card, today's default) or "stream" (live MJPEG)
latest_jpeg_frame = None
bot_running = False        # swim gait + obstacle avoidance on/off, dashboard toggle
                            # -- starts off; flip on from the dashboard once you're
                            # ready (avoids the fish immediately swimming/thrashing
                            # on every boot/service restart before anyone's watching)
servo_test_requested = False
servo_test_status = "idle"     # "idle" | "running" | "complete" | "error: ..."
camera_test_requested = False
camera_test_status = "idle"
camera_test_path = None
_lock = threading.Lock()


def get_distance():
    with _lock:
        return latest_distance_cm


def get_distance_history():
    with _lock:
        return list(distance_history)


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


def get_bot_running():
    with _lock:
        return bot_running


def set_bot_running(value):
    global bot_running
    with _lock:
        bot_running = value


def request_servo_test():
    global servo_test_requested, servo_test_status
    with _lock:
        if servo_test_status == "running":
            return False
        servo_test_requested = True
        servo_test_status = "running"
        return True


def get_servo_test_status():
    with _lock:
        return servo_test_status


def request_camera_test():
    global camera_test_requested, camera_test_status
    with _lock:
        if camera_test_status == "running":
            return False
        camera_test_requested = True
        camera_test_status = "running"
        return True


def get_camera_test_status():
    with _lock:
        return camera_test_status, camera_test_path


def sensor_loop(obs):
    global latest_distance_cm
    while True:
        d = obs.distance_cm()
        now = time.time()
        with _lock:
            latest_distance_cm = d
            distance_history.append((now, d))
        time.sleep(0.1)


def run_servo_sweep_test(fish):
    """
    Quick per-joint sweep triggered by the dashboard's "Test Servos" button
    -- same idea as test_servos.py's sweep_one() but shorter, since it runs
    inline in swim_loop and pauses the gait for its duration.
    """
    fish.center_all()
    time.sleep(0.3)
    for i in range(len(SERVO_CHANNELS)):
        for angle in range(CENTER_ANGLE, SERVO_TEST_SWEEP_LOW, -2):
            fish.set_angle(i, angle)
            time.sleep(SERVO_TEST_STEP_DELAY_S)
        for angle in range(SERVO_TEST_SWEEP_LOW, SERVO_TEST_SWEEP_HIGH + 1, 2):
            fish.set_angle(i, angle)
            time.sleep(SERVO_TEST_STEP_DELAY_S)
        for angle in range(SERVO_TEST_SWEEP_HIGH, CENTER_ANGLE - 1, -2):
            fish.set_angle(i, angle)
            time.sleep(SERVO_TEST_STEP_DELAY_S)
    fish.center_all()


def swim_loop(fish):
    global servo_test_requested, servo_test_status
    start = time.time()
    was_running = True
    while True:
        with _lock:
            do_test = servo_test_requested
            servo_test_requested = False

        if do_test:
            try:
                run_servo_sweep_test(fish)
                with _lock:
                    servo_test_status = "complete"
            except Exception as exc:
                with _lock:
                    servo_test_status = f"error: {exc}"
            start = time.time()
            was_running = True
            continue

        running = get_bot_running()
        if not running:
            if was_running:
                fish.idle_all()
                was_running = False
            time.sleep(0.1)
            continue
        if not was_running:
            start = time.time()  # reset gait phase so it doesn't jump on resume
            was_running = True

        d = get_distance()
        turn_bias = 0.0
        if d is not None and d < AVOID_THRESHOLD_CM:
            turn_bias = 1.0  # turn away when something is close ahead
        fish.swim_step(time.time() - start, turn_bias=turn_bias)
        time.sleep(0.02)


def camera_loop(cam):
    """
    Runs the camera in whichever mode the dashboard toggle last selected.
    Only one mode is ever active on the camera at once -- switching modes,
    or running the dashboard's "Test Camera" self-test, cleanly stops the
    previous activity before starting the next.
    """
    global latest_jpeg_frame, camera_test_requested, camera_test_status, camera_test_path
    active_mode = None
    recording_deadline = 0

    while True:
        with _lock:
            do_test = camera_test_requested
            camera_test_requested = False

        if do_test:
            try:
                if active_mode == "record":
                    cam.stop_recording()
                elif active_mode == "stream":
                    cam.stop_stream()
                filename = f"dashboard_test_{int(time.time())}.jpg"
                path = cam.capture_still(filename)
                with _lock:
                    camera_test_status = "complete"
                    camera_test_path = str(path)
            except Exception as exc:
                with _lock:
                    camera_test_status = f"error: {exc}"
            active_mode = None  # force a clean restart of the current mode below
            continue

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

    app = create_app(
        get_distance=get_distance,
        get_camera_mode=get_camera_mode,
        set_camera_mode=set_camera_mode,
        get_jpeg_frame=get_jpeg_frame,
        get_bot_running=get_bot_running,
        set_bot_running=set_bot_running,
        get_distance_history=get_distance_history,
        request_servo_test=request_servo_test,
        get_servo_test_status=get_servo_test_status,
        request_camera_test=request_camera_test,
        get_camera_test_status=get_camera_test_status,
        captures_dir=CAPTURES_DIR,
    )
    try:
        # threaded=True: lets the long-lived MJPEG stream connection and the
        # short distance-polling/test requests be served concurrently -- see
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
