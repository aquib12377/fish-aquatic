"""
Test Camera -- standalone bring-up test for the Camera Module Rev 1.3.

Confirms the camera is detected, captures a still, and records a short
test video -- both written to the SD card under captures/ and recordings/.

    source ~/fishenv/bin/activate
    python3 test_camera.py
"""
import time
from picamera2 import Picamera2
from camera_module import FishCamera

TEST_VIDEO_SECONDS = 5


def print_camera_info():
    info = Picamera2.global_camera_info()
    if not info:
        print(
            "No camera detected. Check:\n"
            "  - the ribbon is the Pi Zero-specific CSI cable (narrow connector "
            "at the Pi end), not the standard cable that ships with the camera\n"
            "  - the ribbon is seated the right way round at BOTH ends "
            "(contacts facing the board at the Pi end, facing the PCB at the "
            "camera end)\n"
            "  - `rpicam-hello --list-cameras` from the shell agrees"
        )
        return False
    print("Detected camera(s):")
    for cam in info:
        print(f"  {cam}")
    return True


def main():
    if not print_camera_info():
        return

    cam = FishCamera()

    print("\nCapturing a still image...")
    still_path = cam.capture_still("test_still.jpg")
    print(f"  saved: {still_path.resolve()}  ({still_path.stat().st_size} bytes)")

    print(f"\nRecording a {TEST_VIDEO_SECONDS}s test video to the SD card...")
    video_path = cam.start_recording_to_file("test_video.mp4")
    time.sleep(TEST_VIDEO_SECONDS)
    cam.stop_recording()
    print(f"  saved: {video_path.resolve()}  ({video_path.stat().st_size} bytes)")

    cam.close()
    print("\nCamera test complete. Copy these off the Pi to check playback, e.g.:")
    print(f"  scp pi@<pi-ip>:{still_path.resolve()} .")
    print(f"  scp pi@<pi-ip>:{video_path.resolve()} .")


if __name__ == "__main__":
    main()
