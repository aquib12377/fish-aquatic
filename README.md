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
6. **Enable a USB rescue console now, while you still have easy access** —
   this costs nothing and pays off the moment WiFi ever locks you out (see
   below). It turns the Zero W's USB data port into a direct wired network
   link to a computer, independent of WiFi entirely:
   ```bash
   echo "dtoverlay=dwc2" | sudo tee -a /boot/firmware/config.txt
   sudo sed -i 's/\brootwait\b/rootwait modules-load=dwc2,g_ether/' /boot/firmware/cmdline.txt
   sudo reboot
   ```
   (If you're doing this from another computer instead, with the SD card in
   a reader: the same two files sit at the *root* of the boot partition —
   just named `config.txt` and `cmdline.txt`, no `/boot/firmware/` prefix —
   plus create an empty file named `ssh` there too in case SSH ever needs
   re-enabling.) After a reboot, plug a USB cable into the Pi's **USB**
   port (not `PWR IN`) and a computer, wait ~30-60s, then
   `ssh pi@raspberrypi.local` works over that cable even if WiFi is
   completely dead — no HDMI/keyboard or re-flashing required. Safe to
   leave enabled permanently; it only does anything when that port is
   actually plugged into a computer.

**WiFi won't connect to a phone hotspot (or the WiFi LED blinks but it
never associates):** if you can't reach the Pi over WiFi at all to run any
of the commands below, and you enabled the USB rescue console in step 6
above, plug in the USB cable and `ssh` in over that first — everything
here works the same way once you have any shell on the Pi, wired or
wireless. Otherwise you'll need to pull the SD card and enable it now (see
step 6). Before suspecting the Pi or the hotspot app, check these, roughly
in order of how often they're the actual cause:

- **Band mismatch — the single most common cause.** The Zero W's onboard
  chip (BCM43438) is **2.4GHz 802.11 b/g/n only** — it has no 5GHz radio at
  all. Many phones default their hotspot to 5GHz, or to an "auto"/"smart"
  band that steers modern devices onto 5GHz, and the Zero W simply cannot
  see that network — it's not a matter of retrying longer. In the phone's
  hotspot settings, force the band to **2.4GHz only** (Android: Settings →
  Hotspot & tethering → AP band; iPhone hotspots are 2.4GHz by default
  already, so this is mostly an Android issue).
- **No WLAN country code set** → NetworkManager/`wpa_supplicant` soft-blocks
  the radio (`rfkill`) rather than connecting at all. Check with
  `rfkill list wifi`; if it shows `Soft blocked: yes`, set it via
  `sudo raspi-config` → Localisation Options → WLAN Country (must match
  where you actually are), or `sudo rfkill unblock wifi`.
- **Credentials pre-configured in Imager don't match** — if you changed the
  hotspot password after writing the SD card, or pre-configured the wrong
  SSID, the Pi will keep retrying with stale credentials and look like it's
  "trying forever." Reconfigure via `sudo nmtui` (Bookworm's default,
  NetworkManager) or `sudo raspi-config` → System Options → Wireless LAN.
- **Weak signal / hotspot out of range** — the Zero W's PCB antenna is
  modest; keep the phone within a few meters for initial setup, especially
  once the Pi is sealed inside the fish body.
- **Diagnose what's actually happening** rather than guessing further:
  ```bash
  nmcli device wifi list        # does the hotspot even show up in a scan?
  nmcli device status           # is wlan0 "connecting", "unavailable", or "disconnected"?
  journalctl -u NetworkManager -b --no-pager | tail -50
  dmesg | grep -i brcmfmac      # driver-level errors (firmware load failures, etc.)
  ```
  If the hotspot doesn't show up in `nmcli device wifi list` at all, that's
  the band mismatch above, not a credentials or timing problem.

**If a phone hotspot still won't cooperate, flip it around: make the Pi
its own hotspot instead of joining one.** This sidesteps every problem
above — band settings, credentials, phone-side quirks — because you're no
longer depending on someone else's network at all; your phone/laptop
connects *to the fish's* WiFi network directly. Bookworm's NetworkManager
has this built in, no extra packages needed:

```bash
sudo nmcli device wifi hotspot ifname wlan0 ssid FishRobot password "pick-a-password"
```

That both creates and immediately activates a `Hotspot` connection profile
(2.4GHz, since that's all the Zero W's radio does anyway — no band
mismatch is possible now). The Pi is reachable at `192.168.4.1` from
whatever device just joined the `FishRobot` network — browse to
`http://192.168.4.1:5000/` for the dashboard instead of `hostname -I`'s
address from §9.

To make it come up automatically on every boot instead of running that
command by hand each time:

```bash
sudo nmcli connection modify Hotspot connection.autoconnect yes \
                                       connection.autoconnect-priority 100
```

The tradeoffs, so you can decide which mode fits how you'll actually use
this: in hotspot mode the Pi has no internet access itself (fine — nothing
in `main.py`/`web_dashboard.py` needs internet, only LAN reachability to
whatever's connected), and only one device can be joined to it at a time
on the Zero W's single radio, same limit either direction. If you'd rather
switch back to joining an existing network later, `sudo nmtui` lets you
add a regular WiFi connection alongside the `Hotspot` profile and pick
which one is active.

This is separate from — but often confused with — the *service startup*
delay covered in §10: even once WiFi is fixed and connecting reliably, a
slow *initial* association after power-on is normal (retry/backoff, DHCP
negotiation), which is why `fish-robot.service` no longer blocks the whole
robot on network coming up (§10).

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

Only move on to `python3 main.py` once all three pass. See **TESTING.md**
for what correct output looks like at each step, concrete troubleshooting
for each script, and how to test the web dashboard (§9) once `main.py` is
running.

## 8. Camera: continuous video saved to the SD card

The camera has two mutually exclusive modes, selected at runtime from the
web dashboard (§9): **record** (this section — the default, segmented
H264->mp4 saved to the SD card) and **stream** (live MJPEG feed in the
browser instead, see §9). Only one runs at a time — switching modes cleanly
stops whichever is active before starting the other, since Picamera2 can't
drive the sensor for both at once on this hardware.

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

## 9. Web dashboard

`main.py` is the **single entry point** for the whole robot: it starts the
servo swim gait, obstacle-avoidance loop, sensor polling, and camera thread
exactly as before, and additionally serves a small Flask dashboard on
`0.0.0.0:5000` so any device on the same LAN/WiFi can reach it at:

```
http://<pi-ip>:5000/
```

(`hostname -I` on the Pi prints its IP.) `web_dashboard.py` is a library —
it builds the Flask app but never touches hardware directly and is not run
standalone; `main.py` imports it and wires it to the same
daemon-thread-plus-lock shared state (`latest_distance_cm`, etc.) that the
swim/obstacle loop already used, rather than introducing a different
concurrency model.

The dashboard shows:

- **Live ultrasonic distance**, polled from a `GET /api/distance` JSON
  endpoint once a second and updated in the page without a reload.
  Websockets/SSE weren't worth the complexity for one slow-changing number.
- **A camera mode toggle** (`GET`/`POST /api/camera_mode`) between:
  - **Save to SD Card** — today's segmented H264->mp4 recording (§8),
    unchanged behavior, still pruned by `prune_old_recordings()`.
  - **Live Stream** — an MJPEG feed (`GET /stream.mjpg`) embedded directly
    in the page as an `<img>` tag, at a deliberately modest resolution and
    ~5 fps (`STREAM_FPS` in `web_dashboard.py`) — see the caveats below.
- **A bot Start/Stop switch** (`GET`/`POST /api/bot_state`, `{"running": bool}`).
  The bot **starts off** (`bot_running = False` in `main.py`) every time
  `main.py` launches or restarts — servos idle, nothing swimming — so it
  never starts thrashing unattended on boot; flip it on from the dashboard
  once you're actually watching it. Stopping pauses only the swim gait —
  `swim_loop` calls the new `FishServoController.idle_all()` once so the
  servos go limp (no buzzing) instead of holding a pose, then resumes the
  gait's phase cleanly from zero when restarted. The sensor loop, camera,
  and dashboard itself keep running while stopped — this is a "hold still"
  switch for the body, not a process kill switch (use `Ctrl+C` or
  `systemctl stop`, §10, for that).
- **Component self-tests**, so you can sanity-check hardware from a browser
  without SSHing in:
  - **Test Servos** (`POST /api/test/servos`) briefly pauses the gait and
    runs a short sweep of each joint (reusing the running `FishServoController`
    — it does not open a second connection to the PCA9685), then resumes
    whatever the bot's on/off state was.
  - **Test Ultrasonic** (`GET /api/test/ultrasonic`) is non-destructive —
    it summarizes (min/max/avg) a rolling ~5s buffer of readings the sensor
    loop already collects, so it's safe to poll repeatedly and doesn't touch
    the sensor directly.
  - **Test Camera** (`POST /api/test/camera`) briefly interrupts the
    current recording/streaming mode, captures one still into `captures/`
    (reusing `FishCamera.capture_still()`), then resumes the previous
    camera mode automatically. The captured image is served back at
    `GET /captures/<filename>` and shown inline on the page.
  - Each test's status (`idle`/`running`/`complete`/`error: ...`) is
    polled from the same endpoint the trigger POST hits; a second trigger
    while one is already running gets `409`.

  The servo gait and obstacle avoidance loop keep running regardless of
  which camera mode is selected; the toggle only affects the camera. All of
  this shares the original `_lock`-guarded globals in `main.py` — no new
  concurrency model, just more state under the same lock.

Run it the same way as before — nothing new to install beyond
`pip install -r requirements.txt` picking up Flask:

```bash
source ~/fishenv/bin/activate
python3 main.py
```

See **TESTING.md** for step-by-step verification (confirming the distance
reading actually updates live, confirming the toggle really switches modes
and recordings still land in `recordings/`, viewing the stream from
another device, exercising the bot Start/Stop switch, and running each
component self-test).

## 10. Running on boot (systemd)

`fish-robot.service` in this repo is a ready-to-use systemd unit that
starts `main.py` on boot using the `fishenv` venv's own Python
interpreter (equivalent to activating the venv, since a venv's `python3`
already has the venv's packages on `sys.path` — systemd units can't
`source activate.sh`), restarts it if it crashes, and sends its output to
the journal.

```ini
[Unit]
Description=Robotic fish (swim gait, obstacle avoidance, camera, web dashboard)
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/fish_robot
ExecStart=/home/pi/fishenv/bin/python3 /home/pi/fish_robot/main.py
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

**Why it doesn't `Wants=network-online.target`:** earlier versions of this
unit waited on `network-online.target`, which is why boot could appear to
"take a long time to connect to the hotspot" — systemd was actually
blocking `main.py` from starting at all until the WiFi interface finished
associating with the hotspot *and* got a full DHCP lease, which on a phone
hotspot can take anywhere from several seconds to a minute or more
(association retries with backoff if the hotspot wasn't up yet, plus
whatever `NetworkManager-wait-online`/`dhcpcd`'s own wait timeout is), and
the servos/camera/obstacle-avoidance sat idle the whole time even though
none of that needs a network connection. Only the Flask dashboard needs
WiFi, and Flask binding `0.0.0.0:5000` doesn't require the interface to
already have an address — the dashboard simply becomes reachable a moment
after the WiFi link comes up, no restart needed. So the unit now only
orders itself after basic network stack init (`network.target`, which
doesn't block on a connection), and the robot starts swimming immediately
at boot regardless of how long WiFi takes.

This fixes the *robot* being stuck waiting — it does not fix WiFi that
never connects at all (band mismatch, stale credentials, blocked radio).
If the dashboard never becomes reachable and WiFi genuinely won't
associate (not just slow), see the WiFi/hotspot troubleshooting steps in
§5 — the Zero W's 2.4GHz-only radio and phones that default their hotspot
to 5GHz is the most common cause of that.

If your username, venv path, or code directory differ from the defaults
assumed above (`pi`, `~/fishenv`, `~/fish_robot`), edit `User=`,
`ExecStart=`, and `WorkingDirectory=` in `fish-robot.service` before
installing it — relative paths like `recordings/` are resolved against
`WorkingDirectory`.

Install and enable it:

```bash
sudo cp fish-robot.service /etc/systemd/system/fish-robot.service
sudo systemctl daemon-reload
sudo systemctl enable fish-robot.service
sudo systemctl start fish-robot.service
```

Check status and logs:

```bash
sudo systemctl status fish-robot.service
journalctl -u fish-robot.service -f       # follow logs live
journalctl -u fish-robot.service -n 100   # last 100 lines
```

`Restart=on-failure` means a crash (e.g. a transient I2C or camera error)
restarts the whole robot after 5s rather than leaving it dead until someone
notices — the same daemon-thread design means a crash in one subsystem's
Python thread still takes down the whole process, so systemd's restart is
the recovery mechanism, not in-process error handling.

**`ModuleNotFoundError: No module named 'flask'` (or any other package) in
`journalctl`:** the venv at `~/fishenv` doesn't have that package installed —
usually because the code was updated (`git pull`/`scp`/`rsync`, §6) after
`requirements.txt` changed, but `pip install -r requirements.txt` was never
re-run in the venv to match. Fix it and restart:

```bash
source ~/fishenv/bin/activate
pip install -r ~/fish_robot/requirements.txt
deactivate
sudo systemctl restart fish-robot.service
```

`systemctl start`/`restart` don't activate the venv for you — they invoke
`~/fishenv/bin/python3` directly per `ExecStart=` above, so an out-of-date
venv fails the same way every restart until it's reinstalled. Make
`pip install -r requirements.txt` (§5) part of your normal update routine
whenever you pull code that touches `requirements.txt`, not just on first
setup.

## 11. Caveats — please read all of these before assembly

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

**Web dashboard (new):**

- **The dashboard has no authentication.** Anyone who can reach the Pi's IP
  on the same WiFi/LAN — not just you — can view the live distance reading
  and camera stream and flip the recording/streaming toggle at
  `http://<pi-ip>:5000/`. Don't run this on a network you don't trust (a
  shared/public WiFi, an open guest network) without adding your own
  auth in front of it; nothing here does that for you.
- **One ARM11 core has real limits.** Flask, MJPEG streaming, the servo
  swim-gait loop, and ultrasonic polling all share the Pi Zero W's single
  core. The defaults (640×480 MJPEG at `STREAM_FPS = 5` in
  `web_dashboard.py`) are deliberately modest — raising resolution/framerate
  much further can start starving the servo loop of CPU time and making the
  gait stutter. If you need higher-quality video, prefer SD-card recording
  mode (hardware-encoded, much lighter — see §8) over pushing live-stream
  quality up.
- Recording and streaming are mutually exclusive by design (§8/§9) — don't
  expect to record to the SD card and watch a live view at the same time.
- **The dashboard's Stop switch and self-tests can move the fish or briefly
  interrupt recording/streaming.** Anyone who can reach the dashboard can
  trigger the servo self-test (moves all 4 joints for a few seconds) or the
  camera self-test (drops the active recording/stream for roughly a
  second while it grabs a still). Harmless, but don't be surprised by
  unexpected servo motion or a one-frame gap in a recording if someone else
  on the network is poking at the dashboard.

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

## 12. Files

- `servo_controller.py` — PCA9685 + 4-servo travelling-wave swim gait (library)
- `ultrasonic_sensor.py` — AJ-SR04M Mode 1 reader (library)
- `camera_module.py` — Picamera2 still/video capture, SD-card recording, and
  MJPEG streaming (library)
- `web_dashboard.py` — Flask web dashboard: live distance readout + camera
  mode toggle (library, built by and run from `main.py`)
- `test_servos.py` — standalone servo bring-up test
- `test_ultrasonic.py` — standalone ultrasonic bring-up test
- `test_camera.py` — standalone camera bring-up test (still + short video)
- `main.py` — **single entry point.** Ties everything together: swim, steer
  away from obstacles, run the camera in record-or-stream mode, and serve
  the web dashboard
- `requirements.txt` — pip dependencies (picamera2 and ffmpeg install via apt, see §5)
- `fish-robot.service` — systemd unit for running `main.py` on boot, see §10
- `TESTING.md` — detailed bring-up test walkthroughs, troubleshooting, and
  web dashboard verification steps
