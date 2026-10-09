
import time
from pathlib import Path

from gpiozero import Device, PWMOutputDevice, DigitalOutputDevice
from gpiozero.pins.lgpio import LGPIOFactory

# Use the existing LGPIO pin factory
Device.pin_factory = LGPIOFactory()

# GPIO BCM pin numbers
ENA = 18
IN1 = 17
IN2 = 27
IN3 = 22
IN4 = 23
ENB = 24

COMMAND_FILE = Path(__file__).with_name("motor_command.txt")

# Speed settings: 0.0 to 1.0
FORWARD_SPEED = 0.50
TURN_SPEED = 0.35

# Stop if the command file stops updating for too long.
# The camera script should refresh it continuously.
COMMAND_TIMEOUT = 2.0

# Motor driver outputs
ena = PWMOutputDevice(ENA, frequency=1000, initial_value=0)
enb = PWMOutputDevice(ENB, frequency=1000, initial_value=0)

in1 = DigitalOutputDevice(IN1, initial_value=False)
in2 = DigitalOutputDevice(IN2, initial_value=False)
in3 = DigitalOutputDevice(IN3, initial_value=False)
in4 = DigitalOutputDevice(IN4, initial_value=False)

last_command = None

def stop_motors():
    ena.value = 0
    enb.value = 0

    in1.off()
    in2.off()
    in3.off()
    in4.off()

def set_forward(speed):
    in1.on()
    in2.off()
    in3.on()
    in4.off()

    ena.value = speed
    enb.value = speed

def set_left(speed):
    # Pivot left
    in1.off()
    in2.on()
    in3.on()
    in4.off()

    ena.value = speed
    enb.value = speed

def set_right(speed):
    # Pivot right
    in1.on()
    in2.off()
    in3.off()
    in4.on()

    ena.value = speed
    enb.value = speed

def apply_command(command):
    if command == "FORWARD":
        set_forward(FORWARD_SPEED)
    elif command == "LEFT":
        set_left(TURN_SPEED)
    elif command == "RIGHT":
        set_right(TURN_SPEED)
    else:
        stop_motors()

print("Motor bridge ready.", flush=True)
print(f"Forward speed: {FORWARD_SPEED:.0%}", flush=True)
print(f"Turn speed: {TURN_SPEED:.0%}", flush=True)
print("Commands: FORWARD, LEFT, RIGHT, STOP", flush=True)

try:
    stop_motors()

    while True:
        try:
            command = COMMAND_FILE.read_text().strip().upper()
            file_age = time.time() - COMMAND_FILE.stat().st_mtime
        except (OSError, ValueError):
            command = "STOP"
            file_age = float("inf")

        # Fail-safe if the camera process crashes or stops updating.
        if file_age > COMMAND_TIMEOUT:
            command = "STOP"

        if command not in ("FORWARD", "LEFT", "RIGHT", "STOP"):
            command = "STOP"

        if command != last_command:
            apply_command(command)
            print(f"Command: {command}", flush=True)
            last_command = command

        time.sleep(0.05)

except KeyboardInterrupt:
    print("\nStopping motor bridge...", flush=True)

finally:
    stop_motors()

    ena.close()
    enb.close()
    in1.close()
    in2.close()
    in3.close()
    in4.close()

    print("Motors stopped; GPIO released.", flush=True)
