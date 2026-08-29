# Testing guide

This extends README.md §7 with what correct output looks like at each step
and concrete troubleshooting for failure modes specific to this hardware.
Run the three standalone tests below **before** `main.py`, and read
README.md's wiring/power sections first if you haven't wired everything up
yet.

```bash
source ~/fishenv/bin/activate
cd ~/fish_robot   # or wherever you copied the files, see README §6
```

## 1. `test_servos.py`

```bash
python3 test_servos.py
```

**What correct behavior looks like:**
- "Connecting to PCA9685..." prints with no exception (an exception here
  means the I2C connection itself failed, not a servo problem).
- All 4 joints snap to a level, centered position.
- Each joint sweeps individually, head to tail, while the other 3 stay put
  and don't buzz or twitch.
- The final 5s combined swim gait looks like a smooth travelling wave from
  head to tail, not all 4 joints moving in lockstep.

**Troubleshooting:**

| Symptom | Likely cause |
|---|---|
| `ValueError` / `OSError` connecting to the PCA9685, or script hangs at "Connecting..." | I2C not enabled (`sudo raspi-config` → Interface Options → I2C), wrong SDA/GPIO2, SCL/GPIO3 wiring, or the board genuinely isn't on the bus — run `i2cdetect -y 1` and confirm `40` appears. A blank grid means a wiring problem, not a software one. |
| The wrong joint moves during a given channel's sweep | The servo is plugged into a different PCA9685 channel than `SERVO_CHANNELS` in `servo_controller.py` expects (0=head, 3=tail by default). Either replug the servo to match, or reorder `SERVO_CHANNELS`. |
| A joint grinds, stalls, or the sweep looks clipped near 45°/135° | Mechanical end-stop reached before the commanded angle — the servo horn or linkage is binding. Reduce `SWEEP_LOW`/`SWEEP_HIGH` in `test_servos.py`, or recalibrate `SERVO_MIN_PULSE`/`SERVO_MAX_PULSE` in `servo_controller.py` per README §9. |
| All 4 joints twitch/jitter together, in sync with something else running | Something else on the Pi is loading the CPU heavily enough to matter, or a poor/undersized servo power supply is browning out under load — check §3 (power architecture) sizing, not the code. |
| Servo buzzes continuously even when the script isn't actively moving it | Normal while a joint holds a commanded angle (analog servos need a continuous refresh signal). It should stop once `fish.release()` runs at the end — if it doesn't, the script was interrupted before reaching `finally:` (e.g. killed with `SIGKILL` instead of Ctrl+C). |

## 2. `test_ultrasonic.py`

```bash
python3 test_ultrasonic.py
```

**What correct behavior looks like:**
- 15s of readings print, roughly 4/sec.
- Waving a flat object (a book, your hand) in front of the sensor visibly
  changes the printed number within a fraction of a second.
- The min/max/avg summary at the end shows a sensible spread, not a single
  repeated value.

**Troubleshooting:**

| Symptom | Likely cause |
|---|---|
| Every reading is `0.0 cm` | ECHO wired without the voltage divider (or the divider values are swapped), TRIG/ECHO pins reversed, or a dead sensor. Re-check against README §4 before assuming the module is faulty. |
| Every reading is stuck at the max range (400.0 cm at the default `MAX_RANGE_M`) | Nothing in range (expected if you're not testing in front of it), the sensor isn't receiving its own echo (probe pointed at something absorptive/angled away), or ECHO genuinely isn't reaching the GPIO — try holding a flat, hard object very close (10–20cm) and confirm the number drops. If it never drops, treat it the same as "stuck at 0": recheck wiring. |
| Readings jump around wildly / don't correlate with what's actually in front of the sensor | Missing common ground between the Pi, PCA9685, and sensor supply (README §3) — this is the single most common cause of "noisy I2C and noisy ultrasonic" appearing together. Also check the sensor is Mode 1 (trigger/echo), not accidentally wired for Mode 2 (UART). |
| `gpiozero.exc.*` exception on startup | Usually a pin factory / permissions issue unrelated to the sensor itself — confirm `gpiozero` and `RPi.GPIO` installed correctly in the venv (`pip list` inside the activated venv), and that you're not running as a user without GPIO access. |
| Readings look plausible in air but nonsense when the probe is wet/submerged | Expected, not a bug — see README §9's aquatic caveat. This sensor's timing assumes the speed of sound in air; it isn't meant to read distance through water. |

## 3. `test_camera.py`

```bash
python3 test_camera.py
```

**What correct behavior looks like:**
- "Detected camera(s):" prints at least one entry.
- A still image saves to `captures/test_still.jpg` with a non-zero byte size.
- A 5s video saves to `recordings/test_video.mp4` with a non-zero byte size.
- Copying both off the Pi (`scp`, see the script's own printed commands) and
  opening them plays back a normal image/video, not a corrupt file.

**Troubleshooting:**

| Symptom | Likely cause |
|---|---|
| "No camera detected" | Almost always the ribbon cable: wrong cable (needs the Pi Zero-specific narrow-connector CSI cable, not the standard one that ships with the camera), inserted backwards at one end, or not fully seated. Reseat both ends and re-run `rpicam-hello --list-cameras` directly from the shell to confirm outside of Python. |
| Camera detected, but `capture_still()`/`start_recording_to_file()` raises an exception | Legacy camera stack enabled by mistake (`raspi-config` → Interface Options → Legacy Camera should be **disabled** — Picamera2 needs the modern libcamera stack), or `python3-picamera2`/`python3-libcamera` weren't installed via apt into a venv that has `--system-site-packages` (see README §5). |
| Video file exists but is 0 bytes or won't play | `ffmpeg` not installed (`sudo apt install -y ffmpeg`) — `FfmpegOutput` needs it on the PATH to mux the raw H264 stream into a playable `.mp4`. |
| Still image looks washed out / very dark | Normal on first capture if the 1s AE/AWB settle in `capture_still()` isn't enough for your lighting — re-run, or increase the `time.sleep(1)` in `camera_module.py` for a difficult lighting setup. |

Only move on to `python3 main.py` once all three pass.

## 4. Web dashboard

Start the full robot (this also starts the dashboard):

```bash
python3 main.py
```

Find the Pi's IP with `hostname -I` on the Pi, then from **any other device
on the same WiFi/LAN**, browse to:

```
http://<pi-ip>:5000/
```

(Not from the Pi's own SD card recording setup — this is a separate HTTP
server, no relation to `recordings/`.)

**Confirm the live distance reading actually updates:**
- The number on the page should change within ~1 second of waving an object
  in front of the ultrasonic sensor, without you refreshing the page.
- If it's stuck, open the browser's dev tools → Network tab and check that
  `GET /api/distance` requests are succeeding (should return
  `{"distance_cm": <number or null>}` every second). A `null` value most of
  the time means the sensor loop hasn't produced a reading yet — if it
  never becomes a number, re-run `test_ultrasonic.py` standalone first.

**Confirm the toggle actually switches camera modes:**
1. On page load, the mode should default to **Save to SD Card** (today's
   behavior).
2. `ls -la recordings/` on the Pi — you should see a `.mp4` file with a
   recent/advancing modification time.
3. Click **Live Stream** on the dashboard. Within a couple seconds the page
   should show a live (if low-res/choppy) camera feed. Back on the Pi,
   confirm no *new* recording segments are being written (the most recent
   file's timestamp should stop advancing) — recording genuinely stopped,
   it didn't just keep running in the background.
4. Click **Save to SD Card** again. The live image should disappear, and
   within moments a fresh `.mp4` should appear in `recordings/` with a new,
   advancing timestamp — confirming recording resumed cleanly rather than
   silently staying dead after the mode switch.

**Checking the live stream from another device on the network:**
- Any browser on a phone/laptop on the same WiFi as the Pi can load
  `http://<pi-ip>:5000/` directly — no app or extra software needed, the
  MJPEG stream renders as a plain `<img>` tag.
- If the image never appears: confirm the dashboard's mode toggle actually
  reads "Live Stream" as active (check `GET /api/camera_mode` in dev tools
  — it should return `{"mode": "stream"}`), and check `journalctl` (if
  running under systemd, see README §10) or the terminal running `main.py`
  for Picamera2 errors.
- Expect a soft, low framerate feed (a few frames/second at 640x480) — this
  is intentional, not a bug. See README's caveat on sharing one ARM11 core
  across the servo loop, sensor polling, Flask, and MJPEG encoding.
- Remember: WiFi does not propagate through water (README §9). If the fish
  body is submerged, the dashboard and stream will drop as soon as the
  antenna area goes under.

**Dashboard unreachable at all:**
- Confirm the Pi and your other device are actually on the same
  subnet/WiFi network (a guest network or a phone on cellular data won't
  reach it).
- Confirm `main.py` is actually running and didn't exit — check the
  terminal output or `journalctl -u fish-robot.service` if running as a
  service.
- No firewall is configured by these instructions, but if you've added one
  yourself, make sure TCP port 5000 is allowed.
