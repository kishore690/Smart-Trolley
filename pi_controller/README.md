# Raspberry Pi trolley movement and human following

This is an initial supervised prototype for the Raspberry Pi 4. The Pi controls
the L298N directly; no Arduino is used. Do not run it until the wiring is checked,
the trolley is restrained with its wheels lifted, and a physical power cut is
available.

## Hardware mapping

The existing plan assigns BCM GPIO 17/27 to L298N IN1/IN2 and GPIO 22/23 to
IN3/IN4. This controller assumes the first channel drives the left motor pair
and the second drives the right motor pair. Pair the motors by trolley side, and
confirm their polarities while lifted. If one side runs backward, swap that
side's motor leads with motor power disconnected.

Keep ENA/ENB jumpers fitted for the initial test. With jumpers installed this
prototype can only drive at full channel voltage; its short pulses limit each
movement command. The L298N must be rated for the combined stall current of each
motor pair. Pi ground and driver ground must be common. Motor power must not be
fed from the Pi or from the L298N 5V terminal.

The HC-SR04 trigger and echo pins are intentionally not guessed. Choose unused
BCM pins and wire them only after confirming the board labels. The sensor ECHO
pin is 5V: fit a resistor divider to reduce ECHO to 3.3V before it reaches the
Pi. The program refuses to start until both pin numbers are configured.

## Software

Copy this folder to `/home/kishore/SmartTrolleyAI/pi_controller` on the Pi.
Install `gpiozero` and `lgpio` through Raspberry Pi OS packages, and install
Ultralytics in the project's virtual environment. Use YOLO26n, exported to NCNN
for ARM performance as described in the [Ultralytics Raspberry Pi guide](https://docs.ultralytics.com/guides/raspberry-pi/).
The model path can be overridden with `TROLLEY_PERSON_MODEL`.

After wiring has been confirmed, set `TROLLEY_HCSR04_TRIGGER` and
`TROLLEY_HCSR04_ECHO` to the chosen BCM GPIO numbers, then run the controller
from the Pi terminal. Keep the app/backend and this controller from starting
separate motor-driving processes. Ctrl+C releases all GPIO outputs.

## Behavior and limits

- Detects COCO class `person`, turns toward the largest detection, approaches
  only while the person box is below a starting size threshold, and stops when
  the target is centered and close enough.
- Stops when the camera loses the person, an obstacle is within 40 cm, the
  camera fails, or the sensor/model raises an error.
- The box-size distance threshold is only a starting calibration. A single
  webcam does not measure true range; validate the stopping gap at low speed.
- HC-SR04 readings can miss soft, angled, or narrow obstacles. Add a physical
  emergency stop and do supervised, wheels-raised tests before floor tests.
- This file is not yet wired into the existing FastAPI status endpoint or app.
