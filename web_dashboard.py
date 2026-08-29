"""
Flask web dashboard for the robotic fish.

Shows the live ultrasonic distance reading (polled via a JSON endpoint, no
websockets/SSE needed for a single low-frequency number), a toggle that
switches the camera between "record" (today's segmented H264->mp4 saved to
recordings/) and "stream" (MJPEG live feed embedded in the page), a bot
on/off switch that pauses/resumes the swim gait, and one-shot self-tests
for each subsystem (servos, ultrasonic, camera) so you can sanity-check the
hardware from a browser instead of SSHing in. Only one camera mode runs at
a time -- Picamera2 can't cleanly do both here.

This module does not touch any hardware itself and does not run standalone.
main.py is the single entry point for the whole robot: it owns the servo
gait, obstacle sensor, and camera threads, and calls create_app() here with
plain accessor functions to read/update that shared state. See main.py and
README.md for how it's wired together and started.

CAVEAT: this app has no authentication and binds to 0.0.0.0, so anyone on
the same LAN/WiFi can view the distance reading and camera stream, flip the
recording toggle, pause the bot, or trigger a self-test. Do not expose this
to an untrusted network -- see README.md.
"""
import os
import time
from flask import Flask, Response, jsonify, render_template_string, request, send_from_directory

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
  .row { display: flex; gap: 0.5rem; margin: 0.75rem 0; flex-wrap: wrap; }
  .btn { flex: 1; min-width: 8rem; padding: 0.6rem; border: 1px solid #2c4a63; border-radius: 6px;
              background: #1c3348; color: #e6f0f7; cursor: pointer; font-size: 0.95rem; }
  .btn.active { background: #2f6f9e; border-color: #2f6f9e; }
  .btn.stop { background: #7a2828; border-color: #7a2828; }
  .btn.go { background: #2f7a3e; border-color: #2f7a3e; }
  .btn:disabled { opacity: 0.5; cursor: default; }
  #stream-img { width: 100%; border-radius: 6px; margin-top: 0.75rem; display: none; background: #000; }
  #test-camera-img { width: 100%; border-radius: 6px; margin-top: 0.5rem; display: none; }
  .hint { color: #8fb0c6; font-size: 0.85rem; }
  .status { font-size: 0.9rem; margin-top: 0.4rem; }
  .bot-status { font-size: 1.1rem; font-weight: bold; }
</style>
</head>
<body>
  <h1>Robotic Fish Dashboard</h1>

  <div class="card">
    <div class="hint">Bot (swim gait + obstacle avoidance)</div>
    <div class="row">
      <button id="bot-start" class="btn go" onclick="setBotRunning(true)">Start</button>
      <button id="bot-stop" class="btn stop" onclick="setBotRunning(false)">Stop</button>
    </div>
    <div class="bot-status" id="bot-status">--</div>
    <div class="hint">Stopping only pauses the swim gait (servos go limp) --
      the sensor, camera, and this dashboard keep running.</div>
  </div>

  <div class="card">
    <div class="hint">Ultrasonic distance (obstacle ahead)</div>
    <div class="distance"><span id="distance">--</span><span class="distance-unit"> cm</span></div>
  </div>

  <div class="card">
    <div class="hint">Camera mode</div>
    <div class="row">
      <button id="mode-record" class="btn" onclick="setMode('record')">Save to SD Card</button>
      <button id="mode-stream" class="btn" onclick="setMode('stream')">Live Stream</button>
    </div>
    <img id="stream-img" alt="live camera stream">
    <div class="hint">Live stream is capped at a low resolution/framerate --
      this is a single-core Pi Zero W sharing the CPU with the swim gait and
      sensor loop.</div>
  </div>

  <div class="card">
    <div class="hint">Component self-tests</div>
    <div class="row">
      <button id="test-servos-btn" class="btn" onclick="testServos()">Test Servos</button>
      <button id="test-ultrasonic-btn" class="btn" onclick="testUltrasonic()">Test Ultrasonic</button>
      <button id="test-camera-btn" class="btn" onclick="testCamera()">Test Camera</button>
    </div>
    <div class="status" id="test-servos-status"></div>
    <div class="status" id="test-ultrasonic-status"></div>
    <div class="status" id="test-camera-status"></div>
    <img id="test-camera-img" alt="camera self-test capture">
    <div class="hint">Servo test briefly pauses the gait to sweep each
      joint; camera test briefly interrupts recording/streaming to grab one
      still. Both resume their previous state automatically.</div>
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

function applyBotState(running) {
  document.getElementById('bot-status').textContent = running ? 'Running' : 'Stopped';
  document.getElementById('bot-start').classList.toggle('active', running);
  document.getElementById('bot-stop').classList.toggle('active', !running);
}

async function setBotRunning(running) {
  const r = await fetch('/api/bot_state', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({running: running})
  });
  const data = await r.json();
  applyBotState(data.running);
}

async function initBotState() {
  const r = await fetch('/api/bot_state');
  const data = await r.json();
  applyBotState(data.running);
}

async function testUltrasonic() {
  const el = document.getElementById('test-ultrasonic-status');
  el.textContent = 'sampling...';
  const r = await fetch('/api/test/ultrasonic');
  const data = await r.json();
  if (data.count === 0) {
    el.textContent = 'no readings yet -- is the sensor loop running?';
    return;
  }
  el.textContent = `min ${data.min_cm.toFixed(1)} / avg ${data.avg_cm.toFixed(1)} / ` +
    `max ${data.max_cm.toFixed(1)} cm over last ${data.window_seconds.toFixed(1)}s ` +
    `(${data.count} samples)`;
}

async function pollTestStatus(url, elId, onDone) {
  const el = document.getElementById(elId);
  const r = await fetch(url);
  const data = await r.json();
  el.textContent = 'status: ' + data.status;
  if (data.status === 'running') {
    setTimeout(() => pollTestStatus(url, elId, onDone), 500);
  } else if (onDone) {
    onDone(data);
  }
}

async function testServos() {
  const btn = document.getElementById('test-servos-btn');
  btn.disabled = true;
  const r = await fetch('/api/test/servos', {method: 'POST'});
  if (r.status === 409) {
    document.getElementById('test-servos-status').textContent = 'a test is already running';
    btn.disabled = false;
    return;
  }
  await pollTestStatus('/api/test/servos', 'test-servos-status', () => { btn.disabled = false; });
}

async function testCamera() {
  const btn = document.getElementById('test-camera-btn');
  btn.disabled = true;
  const r = await fetch('/api/test/camera', {method: 'POST'});
  if (r.status === 409) {
    document.getElementById('test-camera-status').textContent = 'a test is already running';
    btn.disabled = false;
    return;
  }
  await pollTestStatus('/api/test/camera', 'test-camera-status', (data) => {
    btn.disabled = false;
    if (data.image_url) {
      const img = document.getElementById('test-camera-img');
      img.src = data.image_url + '?t=' + Date.now();
      img.style.display = 'block';
    }
  });
}

pollDistance();
initMode();
initBotState();
</script>
</body>
</html>
"""


def create_app(
    get_distance,
    get_camera_mode,
    set_camera_mode,
    get_jpeg_frame,
    get_bot_running,
    set_bot_running,
    get_distance_history,
    request_servo_test,
    get_servo_test_status,
    request_camera_test,
    get_camera_test_status,
    captures_dir,
):
    """
    Build the Flask app. All hardware access happens through the accessor
    functions passed in by main.py -- this module never touches the
    sensor/camera/servo objects directly.
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

    @app.route("/api/bot_state", methods=["GET", "POST"])
    def api_bot_state():
        if request.method == "POST":
            data = request.get_json(silent=True) or {}
            running = data.get("running")
            if not isinstance(running, bool):
                return jsonify(error="running must be true or false"), 400
            set_bot_running(running)
        return jsonify(running=get_bot_running())

    @app.route("/api/test/ultrasonic")
    def api_test_ultrasonic():
        history = get_distance_history()
        if not history:
            return jsonify(count=0)
        readings = [d for _, d in history if d is not None]
        if not readings:
            return jsonify(count=0)
        window_seconds = history[-1][0] - history[0][0]
        return jsonify(
            count=len(readings),
            min_cm=min(readings),
            max_cm=max(readings),
            avg_cm=sum(readings) / len(readings),
            latest_cm=readings[-1],
            window_seconds=window_seconds,
        )

    @app.route("/api/test/servos", methods=["GET", "POST"])
    def api_test_servos():
        if request.method == "POST":
            if not request_servo_test():
                return jsonify(status="running", error="already running"), 409
        return jsonify(status=get_servo_test_status())

    @app.route("/api/test/camera", methods=["GET", "POST"])
    def api_test_camera():
        if request.method == "POST":
            if not request_camera_test():
                return jsonify(status="running", error="already running"), 409
        status, path = get_camera_test_status()
        image_url = f"/captures/{os.path.basename(path)}" if path else None
        return jsonify(status=status, image_url=image_url)

    @app.route("/captures/<path:filename>")
    def captures(filename):
        return send_from_directory(str(captures_dir), filename)

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
