# Robotic Fish — RPi Zero W (v1.1, 2017) Build Reference

Based on the [Electromaker robotic fish](https://www.electromaker.io/project/view/robotic-fish-realistic-movement)
concept (Arduino Nano, 4 body-joint servos, IR "eyes", balloon skin), rebuilt
around a Raspberry Pi Zero W for onboard vision + smarter obstacle sensing.

## 1. Bill of materials assumed

- Raspberry Pi Zero W, board rev 1.1 (2017) — single-core ARM11 (BCM2835), ARMv6, 512MB RAM
- PCA9685 16-channel I2C PWM/servo driver breakout
- 4x EMAX ES08MA II analog servo (~12g, metal gear, ~1.8 kg·cm @ 4.8V)
- Raspberry Pi Camera Module Rev 1.3 (OV5647, 5MP)
- AJ-SR04M waterproof-probe ultrasonic distance sensor

## 2. Wiring / pin map

| Signal | Pi Zero W pin | Connects to | Notes |
|---|---|---|---|
| 3.3V | Pin 1 | PCA9685 VCC (logic) | Logic supply only, not servo power |
| GPIO2 / SDA | Pin 3 | PCA9685 SDA | I2C bus 1 |
| GPIO3 / SCL | Pin 5 | PCA9685 SCL | I2C bus 1 |
| GND | Pin 6 (or any GND) | PCA9685 GND + AJ-SR04M GND | **Common ground for everything, including the external servo supply** |
| GPIO23 | Pin 16 | AJ-SR04M TRIG | Direct connection is fine (Pi drives this pin) |
| GPIO24 | Pin 18 | AJ-SR04M ECHO **via divider** | See §4 — never wire ECHO directly to a GPIO |
| CSI connector | — | Camera Rev 1.3 ribbon | Needs the **Pi Zero-specific CSI cable** (narrow 1mm-pitch connector), not the standard cable that ships with the camera |
| External 5–6V supply + | — | PCA9685 **V+** terminal block | Powers all 4 servos — not from the Pi |
| External supply – | — | PCA9685 **V+ terminal GND**, tied into common ground | |
| PCA9685 channel 0–3 headers | — | 4x ES08MA II signal/V+/GND | Each servo plugs straight into a 3-pin channel header |

I2C address: PCA9685 defaults to `0x40`. Confirm with `i2cdetect -y 1` after setup.

## 3. Power architecture (read this before wiring anything)

Two independent supplies, one shared ground:

1. **Pi Zero W** — its own micro-USB 5V source (power bank, wall adapter, or a
   UBEC off your main battery). ~1.2A is the Foundation's stated minimum;
   with WiFi + camera active, give it real headroom.
2. **Servo rail** — a separate 5–6V supply feeding the PCA9685 **V+**
   terminal directly, sized for the *worst case*, not the average. Four
   ES08MA II servos idle at well under 1A combined but can spike toward
   2–3A if two or more stall simultaneously (e.g. a fin hits the tank
   wall). Use a UBEC/BEC rated 3A+, not the Pi's 5V pin — the Zero W's
   onboard regulator is not built to source that.
3. **Tie the grounds together.** The PCA9685, the Pi, and the ultrasonic
   sensor all need a shared 0V reference or the I2C bus and the ECHO
   voltage divider will behave erratically.

## 4. AJ-SR04M level shifting and mode

The AJ-SR04M runs its logic at 5V. GPIO24 (ECHO) **must** go through a
divider or level shifter before reaching the Pi — e.g. a 1kΩ resistor in
series from ECHO to GPIO24, then a 2kΩ resistor from GPIO24 to GND (gives
~3.3V at the Pi from a 5V source). TRIG can be driven directly from the Pi;
3.3V is normally above the sensor's input-high threshold.

The code here uses **Mode 1** (trigger/echo, same protocol as HC-SR04),
selected because it needs no UART. If you instead want **Mode 2**
(continuous UART output), be aware the Zero W's good hardware UART is
shared with Bluetooth by default — you'd need `dtoverlay=disable-bt` and
`enable_uart=1` in `/boot/firmware/config.txt`, and you'd lose onboard BT.
Mode 1 avoids all of that.

## 5. OS setup

The Zero W's SoC is ARMv6 — it does **not** run 64-bit Raspberry Pi OS.
Use the 32-bit image.

1. **Raspberry Pi Imager** → OS: *Raspberry Pi OS Lite (32-bit)*, current
   Bookworm release. In the advanced/gear settings, set hostname, enable
   SSH, and pre-configure WiFi before writing the card.
2. Boot, SSH in, then:
   ```bash
   sudo raspi-config
   ```
   - Interface Options → **I2C** → enable
   - Leave the camera on the default libcamera stack (don't enable "legacy
     camera" — Picamera2 needs the modern stack)
   - Interface Options → **Serial Port** → only if you're doing AJ-SR04M
     Mode 2 (see §4); leave alone for Mode 1
   - Reboot when prompted
3. ```bash
   sudo apt update && sudo apt full-upgrade -y
   sudo apt install -y python3-picamera2 python3-libcamera ffmpeg i2c-tools \
                        python3-pip python3-venv --no-install-recommends
   ```
   (`ffmpeg` is what muxes the camera's raw H264 stream into a playable
   `.mp4` — see §8.)
4. Create the venv with access to the apt-installed camera bindings:
   ```bash
   python3 -m venv --system-site-packages ~/fishenv
   source ~/fishenv/bin/activate
   pip install -r requirements.txt
   ```
5. Verify hardware:
   ```bash
   i2cdetect -y 1        # should show 40 (PCA9685 default address)
   rpicam-hello --list-cameras   # (older images: libcamera-hello)
   ```

## 6. Getting the code onto the Pi

After OS setup, get `README.md` and all the `.py` files onto the Pi, into a
folder like `~/fish_robot/`. A few ways to do it — pick whichever fits your
workflow:

**scp / rsync (simplest, works with what you already have from §5):**
From the machine where you downloaded these files, with the Pi on the same
network and SSH enabled:
```bash
scp -r fish_robot/ pi@<pi-ip-or-hostname>.local:~/
```
or, if you'll be iterating and re-copying as you tweak the code:
```bash
rsync -av fish_robot/ pi@<pi-ip-or-hostname>.local:~/fish_robot/
```
Find `<pi-ip-or-hostname>` with `ping raspberrypi.local`, by checking your
router's client list, or use the hostname you set in Imager's advanced
options directly (`pi@<hostname>.local`) if mDNS/Bonjour resolves on your
network.

**git (if you push this to a repo first):**
```bash
# on the Pi
git clone https://github.com/<you>/fish_robot.git ~/fish_robot
```
Worth it if you'll keep editing the code — `git pull` on the Pi afterward
is faster than re-copying everything each time you change something.

**SFTP GUI (FileZilla, WinSCP, Cyberduck):**
Same SSH credentials as above; drag-and-drop the folder if you'd rather
not use the command line.

**USB flash drive:**
Works, but the Zero W has only one micro-USB **OTG** data port (the other
micro-USB is power-only), so you'd need a USB OTG adapter/hub to plug a
drive in directly — scp is usually less hassle since SSH is already set up.

Whichever method you use, end up with everything in one folder (e.g.
`~/fish_robot/`), then `cd` into it before running the venv setup in §5
and any of the scripts from §7 onward.

## 7. Bring-up tests — run these before main.py

Test each subsystem on its own first. It's much faster to debug one piece
of hardware in isolation than to debug all four at once inside `main.py`.

| Script | What it does |
|---|---|
| `test_servos.py` | Centers all 4 joints, sweeps each one individually (so you can confirm channel-to-joint mapping and check for binding at the travel limits), then runs 5s of the combined swim gait |
| `test_ultrasonic.py` | Prints live distance readings for 15s so you can wave an object in front of the sensor and confirm the numbers respond; prints min/max/avg at the end |
| `test_camera.py` | Confirms the camera is detected, captures a still, and records a 5s test video — both saved to the SD card |

```bash
source ~/fishenv/bin/activate
python3 test_servos.py
python3 test_ultrasonic.py
python3 test_camera.py
```

Only move on to `python3 main.py` once all three pass.

## 8. Camera: continuous video saved to the SD card

`camera_module.py` records H264 video and pipes it live through `ffmpeg`
(via Picamera2's `FfmpegOutput`) into a playable `.mp4`, written directly to
`recordings/` on the Pi's own SD card (relative to wherever you launch the
script — `~/fishenv`'s working directory by default).

- **Encoding is hardware-accelerated.** The BCM2835 has a dedicated H264
  encoder block, so continuous recording stays light on the single ARM11
  core — much lighter than repeatedly encoding JPEG stills would be.
- **`main.py` records in fixed-length segments** (`VIDEO_SEGMENT_SECONDS`,
  default 300s / 5 min) rather than one unbounded file. This bounds each
  file's size and means a power loss mid-recording only risks losing the
  current 5-minute segment, not the whole session.
- **Old segments are pruned automatically** — `MAX_SEGMENTS_KEPT` (default
  24, i.e. ~2 hours at the default segment length) controls how many `.mp4`
  files are kept in `recordings/` before the oldest are deleted. Tune both
  constants in `main.py` to your SD card's free space and how much footage
  you actually want to keep.
- **`test_camera.py`** captures a one-off still + a short test clip to
  `captures/` and `recordings/` so you can confirm playback works before
  running `main.py` for real.

To play a recording back, copy it off the Pi (`scp pi@<ip>:recordings/video_...mp4 .`)
and open it in any standard video player — it's a normal H264-in-MP4 file.

## 9. Caveats — please read all of these before assembly

**Aquatic-specific (the important ones):**

- **The AJ-SR04M will not work as sonar while submerged.** It's a
  non-contact *air-medium* distance sensor — the same family used for
  measuring water level from *above* a tank, not from inside it. Its
  timing assumes sound travels at ~343 m/s (air); underwater it travels at
  ~1480 m/s, so a submerged reading will not be usable distance data even
  if the module doesn't fail outright. If the fish's head sits at or below
  the waterline while "swimming," this sensor needs to be mounted so its
  probe face stays in an air pocket (e.g. behind a sealed acrylic window
  with an air gap) or you'll need a different sensing approach —
  optical/IR (as the original project used), a contact whisker switch, or
  a purpose-built underwater ultrasonic transducer, which is a different
  and more expensive part.
- **None of this electronics is waterproof on its own.** The Pi Zero W,
  PCA9685, camera board, and standard analog servos all need to live in a
  sealed, dry enclosure. Camera needs a clear acrylic/glass window; servo
  output shafts need O-ring or boot seals where they pass through the hull
  to actuate external fins; the AJ-SR04M's cable and probe are the only
  parts rated for wet exposure (check the datasheet — probes are commonly
  IP66/67, the control PCB usually is not).
- **WiFi does not propagate through water.** 2.4GHz is heavily absorbed
  by water. If you want a live control link or video stream while the
  body is submerged, keep the antenna area at or above the waterline. This
  build now records video locally to the SD card instead of streaming it,
  which sidesteps the problem for footage — you just won't get a live feed
  while submerged, only the file afterward.
- **Servo torque vs. water drag.** ~1.8 kg·cm per joint matches what the
  original in-air/shallow-pool design used successfully at a similar
  scale. Water resistance against a larger or stiffer fin than the
  reference balloon-skin design can bog these down — test range of motion
  in water early, before final assembly.

**SD card, since video now records continuously:**

- **Do the storage math before a long run.** At the defaults (640×480,
  4 Mbps), one segment is roughly 4,000,000 × 300 / 8 ≈ 150 MB, so ~30 MB/
  minute, ~1.8 GB/hour. A cheap 8–16GB card fills up faster than you'd
  expect — either lower `VIDEO_BITRATE`/`VIDEO_SIZE` in `camera_module.py`,
  shrink `MAX_SEGMENTS_KEPT` in `main.py`, or use a larger card.
  `prune_old_recordings()` stops the card from silently filling completely,
  but it does so by **deleting your oldest footage**, so treat it as a
  safety net, not a backup strategy.
- **Continuous writes wear an SD card faster than occasional ones.** For
  anything beyond short test sessions, use a card rated for continuous
  recording (e.g. an "endurance" or "high-endurance" microSD, the same
  category used in dashcams/security cameras) rather than a generic
  consumer card.
- **The boot card and the recording card are the same card here.** If
  that's a concern for a long-running deployment, you can point
  `RECORDINGS_DIR` in `camera_module.py` at a mounted USB flash drive
  instead (e.g. `/media/pi/usb-drive/recordings`) so continuous video
  writes don't share wear with the OS partition.
- **Pull footage off regularly.** Nothing here uploads video anywhere —
  it's local-only by design (see the WiFi/water caveat above), so plan to
  `scp`/physically remove the SD card periodically to retrieve footage
  before old segments get pruned.

**Electrical:**

- Never power the servos from the Pi's 5V header pin — see §3.
- Never wire the AJ-SR04M ECHO pin directly to a GPIO — see §4.
- Keep grounds common across the Pi, PCA9685, and sensor supply, or you'll
  get erratic I2C and distance readings.

**Software/platform:**

- Zero W = ARMv6 → 32-bit OS only, as above. Trying a 64-bit image will
  simply fail to boot.
- Legacy `picamera` does not work on current Raspberry Pi OS — this code
  uses Picamera2/libcamera, matching current images.
- Because the PCA9685 generates the servo PWM in its own hardware, servo
  motion stays smooth even if the Pi's single core is briefly busy — this
  is a real advantage of PCA9685 over bit-banging PWM directly from the
  Pi's GPIOs, which would jitter noticeably on a single-core Zero W.
- ES08MA II is an **analog** servo — it needs a continuous refresh signal
  to hold position (the PCA9685 handles this automatically; just be aware
  `angle = None` in the code intentionally stops the pulses so the servo
  goes limp and doesn't buzz when idle).
- Calibrate `SERVO_MIN_PULSE`/`SERVO_MAX_PULSE` per servo before relying
  on the full 0–180° range — mechanical end-stops vary unit to unit, and
  driving past them stresses the plastic/metal gears.

## 10. Files

- `servo_controller.py` — PCA9685 + 4-servo travelling-wave swim gait (library)
- `ultrasonic_sensor.py` — AJ-SR04M Mode 1 reader (library)
- `camera_module.py` — Picamera2 still/video capture + SD-card recording (library)
- `test_servos.py` — standalone servo bring-up test
- `test_ultrasonic.py` — standalone ultrasonic bring-up test
- `test_camera.py` — standalone camera bring-up test (still + short video)
- `main.py` — ties everything together: swim, steer away from obstacles,
  continuously record segmented video to the SD card
- `requirements.txt` — pip dependencies (picamera2 and ffmpeg install via apt, see §5)
