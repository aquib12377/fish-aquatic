"""
RPi Camera Module Rev 1.3 (OV5647, 5MP) capture via Picamera2 / libcamera.

Requires Raspberry Pi OS Bullseye or later, plus ffmpeg for muxing video
into a playable .mp4:
    sudo apt install -y python3-picamera2 ffmpeg --no-install-recommends

Both stills and video are written straight to the Pi's own SD card, under
CAPTURES_DIR / RECORDINGS_DIR (relative to wherever you run the script from).
Video encoding uses the SoC's dedicated hardware H264 encoder block, so
continuous recording stays light on the single ARM11 core -- see README.md
for the SD-card wear/capacity caveats before leaving this running unattended.

start_stream()/get_jpeg_frame()/stop_stream() support the web dashboard's
MJPEG live-view mode (web_dashboard.py) as an alternative to SD-card
recording -- only one of the two runs at a time, see main.py's camera_loop.
"""
import io
import time
from pathlib import Path
from picamera2 import Picamera2
from picamera2.encoders import H264Encoder
from picamera2.outputs import FfmpegOutput

STILL_SIZE = (1296, 972)       # binned 4:3 mode -- see README for why not full 5MP
VIDEO_SIZE = (640, 480)
VIDEO_BITRATE = 4_000_000       # bits/sec -- keep modest, see README storage caveats
CAPTURES_DIR = Path("captures")
RECORDINGS_DIR = Path("recordings")


class FishCamera:
    def __init__(self):
        self.picam2 = Picamera2()
        self.still_config = self.picam2.create_still_configuration(main={"size": STILL_SIZE})
        self.video_config = self.picam2.create_video_configuration(main={"size": VIDEO_SIZE})
        self._recording = False
        self._streaming = False
        CAPTURES_DIR.mkdir(exist_ok=True)
        RECORDINGS_DIR.mkdir(exist_ok=True)

    def capture_still(self, filename=None):
        """Grab a single JPEG still, saved to CAPTURES_DIR on the SD card."""
        self.picam2.configure(self.still_config)
        self.picam2.start()
        time.sleep(1)  # let AE/AWB settle
        filename = filename or f"still_{int(time.time())}.jpg"
        path = CAPTURES_DIR / filename
        self.picam2.capture_file(str(path))
        self.picam2.stop()
        return path

    def start_recording_to_file(self, filename=None, bitrate=VIDEO_BITRATE):
        """
        Start continuous H264 video, muxed live into a playable .mp4 by
        ffmpeg and written straight to RECORDINGS_DIR on the SD card.
        Call stop_recording() to close the file cleanly.
        """
        filename = filename or f"video_{int(time.time())}.mp4"
        path = RECORDINGS_DIR / filename
        self.picam2.configure(self.video_config)
        encoder = H264Encoder(bitrate=bitrate)
        output = FfmpegOutput(str(path))
        self.picam2.start_recording(encoder, output)
        self._recording = True
        return path

    def stop_recording(self):
        if self._recording:
            self.picam2.stop_recording()
            self._recording = False

    def get_frame(self):
        return self.picam2.capture_array()

    def start_stream(self):
        """
        Start the camera running continuously (no encoder/file output) so
        get_jpeg_frame() can be polled for an MJPEG feed. Mutually exclusive
        with recording -- the web dashboard's camera loop stops one before
        starting the other, never both at once.
        """
        self.picam2.configure(self.video_config)
        self.picam2.start()
        self._streaming = True

    def get_jpeg_frame(self):
        """Capture one JPEG-encoded frame. Call start_stream() first."""
        buf = io.BytesIO()
        self.picam2.capture_file(buf, format="jpeg")
        return buf.getvalue()

    def stop_stream(self):
        if self._streaming:
            self.picam2.stop()
            self._streaming = False

    def close(self):
        if self._recording:
            self.stop_recording()
        if self._streaming:
            self.stop_stream()
        self.picam2.close()


def prune_old_recordings(max_files):
    """
    Delete the oldest .mp4 files in RECORDINGS_DIR beyond max_files, so
    continuous recording doesn't silently fill the SD card. Call this after
    each segment finishes -- see main.py's camera_loop.
    """
    RECORDINGS_DIR.mkdir(exist_ok=True)
    files = sorted(RECORDINGS_DIR.glob("*.mp4"), key=lambda p: p.stat().st_mtime)
    while len(files) > max_files:
        oldest = files.pop(0)
        oldest.unlink(missing_ok=True)


# This module is a library -- run test_camera.py to bring up and test the
# hardware, or main.py to run the full robot.
