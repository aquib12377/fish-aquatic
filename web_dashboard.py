"""
Flask web dashboard for the robotic fish.

Shows the live ultrasonic distance reading (polled via a JSON endpoint, no
websockets/SSE needed for a single low-frequency number) and a toggle that
switches the camera between "record" (today's segmented H264->mp4 saved to
recordings/) and "stream" (MJPEG live feed embedded in the page). Only one
camera mode runs at a time -- Picamera2 can't cleanly do both here.

This module does not touch any hardware itself and does not run standalone.
main.py is the single entry point for the whole robot: it owns the servo
gait, obstacle sensor, and camera threads, and calls create_app() here with
plain accessor functions to read/update that shared state. See main.py and
README.md for how it's wired together and started.

CAVEAT: this app has no authentication and binds to 0.0.0.0, so anyone on
the same LAN/WiFi can view the distance reading and camera stream and flip
the recording toggle. Do not expose this to an untrusted network -- see
README.md.
"""
import time
from flask import Flask, Response, jsonify, render_template_string, request

STREAM_FPS = 5   # keep modest -- MJPEG + servo/sensor loops share one ARM11 core

INDEX_HTML = """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Robotic Fish Dashboard</title>
<style>
  body { font-family: sans-serif; max-width: 640px; margin: 2rem auto; padding: 0 1rem; background: #0e1a24; color: #e6f0f7; }
  h1 { font-size: 1.4rem; }
  .card { background: #16283a; border-radius: 8px; padding: 1rem 1.25rem; margin-bottom: 1.25rem; }
  .distance { font-size: 2.5rem; font-weight: bold; }
  .distance-unit { font-size: 1.1rem; color: #8fb0c6; }
  .modes { display: flex; gap: 0.5rem; margin: 0.75rem 0; }
  .mode-btn { flex: 1; padding: 0.6rem; border: 1px solid #2c4a63; border-radius: 6px;
              background: #1c3348; color: #e6f0f7; cursor: pointer; font-size: 0.95rem; }
  .mode-btn.active { background: #2f6f9e; border-color: #2f6f9e; }
  #stream-img { width: 100%; border-radius: 6px; margin-top: 0.75rem; display: none; background: #000; }
  .hint { color: #8fb0c6; font-size: 0.85rem; }
</style>
</head>
<body>
  <h1>Robotic Fish Dashboard</h1>

  <div class="card">
    <div class="hint">Ultrasonic distance (obstacle ahead)</div>
    <div class="distance"><span id="distance">--</span><span class="distance-unit"> cm</span></div>
  </div>

  <div class="card">
    <div class="hint">Camera mode</div>
    <div class="modes">
      <button id="mode-record" class="mode-btn" onclick="setMode('record')">Save to SD Card</button>
      <button id="mode-stream" class="mode-btn" onclick="setMode('stream')">Live Stream</button>
    </div>
    <img id="stream-img" alt="live camera stream">
    <div class="hint">Live stream is capped at a low resolution/framerate --
      this is a single-core Pi Zero W sharing the CPU with the swim gait and
      sensor loop.</div>
  </div>

<script>
async function pollDistance() {
  try {
    const r = await fetch('/api/distance');
    const data = await r.json();
    document.getElementById('distance').textContent =
      (data.distance_cm !== null && data.distance_cm !== undefined)
        ? data.distance_cm.toFixed(1) : '--';
  } catch (e) {
    document.getElementById('distance').textContent = 'err';
  }
  setTimeout(pollDistance, 1000);
}

function applyMode(mode) {
  document.getElementById('mode-record').classList.toggle('active', mode === 'record');
  document.getElementById('mode-stream').classList.toggle('active', mode === 'stream');
  const img = document.getElementById('stream-img');
  if (mode === 'stream') {
    img.src = '/stream.mjpg?t=' + Date.now();
    img.style.display = 'block';
  } else {
    img.removeAttribute('src');
    img.style.display = 'none';
  }
}

async function setMode(mode) {
  const r = await fetch('/api/camera_mode', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({mode: mode})
  });
  const data = await r.json();
  applyMode(data.mode);
}

async function initMode() {
  const r = await fetch('/api/camera_mode');
  const data = await r.json();
  applyMode(data.mode);
}

pollDistance();
initMode();
</script>
</body>
</html>
"""


def create_app(get_distance, get_camera_mode, set_camera_mode, get_jpeg_frame):
    """
    Build the Flask app. All hardware access happens through the four
    accessor functions passed in by main.py -- this module never touches
    the sensor/camera objects directly.
    """
    app = Flask(__name__)

    @app.route("/")
    def index():
        return render_template_string(INDEX_HTML)

    @app.route("/api/distance")
    def api_distance():
        return jsonify(distance_cm=get_distance())

    @app.route("/api/camera_mode", methods=["GET", "POST"])
    def api_camera_mode():
        if request.method == "POST":
            data = request.get_json(silent=True) or {}
            mode = data.get("mode")
            if mode not in ("record", "stream"):
                return jsonify(error="mode must be 'record' or 'stream'"), 400
            set_camera_mode(mode)
        return jsonify(mode=get_camera_mode())

    @app.route("/stream.mjpg")
    def stream_mjpg():
        if get_camera_mode() != "stream":
            return (
                "Live stream not active -- switch camera mode to 'stream' first.",
                409,
            )

        def generate():
            while get_camera_mode() == "stream":
                frame = get_jpeg_frame()
                if frame is None:
                    time.sleep(0.1)
                    continue
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
                )
                time.sleep(1.0 / STREAM_FPS)

        return Response(
            generate(), mimetype="multipart/x-mixed-replace; boundary=frame"
        )

    return app


# This module is a library -- main.py imports create_app() and drives it
# alongside the servo/sensor/camera threads. Don't run this file directly.
