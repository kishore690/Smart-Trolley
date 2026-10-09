
from gpiozero import Device, DigitalOutputDevice, PWMOutputDevice
from gpiozero.pins.lgpio import LGPIOFactory

# Use the working Raspberry Pi GPIO driver
Device.pin_factory = LGPIOFactory()

# BCM GPIO pin numbers
ENA = 18
IN1 = 17
IN2 = 27
ENB = 24
IN3 = 22
IN4 = 23

# Motor speed settings
FORWARD_SPEED = 0.40
TURN_SPEED = 0.30

# Initialize motor driver pins
ena = PWMOutputDevice(ENA, initial_value=0)
enb = PWMOutputDevice(ENB, initial_value=0)

in1 = DigitalOutputDevice(IN1, initial_value=False)
in2 = DigitalOutputDevice(IN2, initial_value=False)
in3 = DigitalOutputDevice(IN3, initial_value=False)
in4 = DigitalOutputDevice(IN4, initial_value=False)


def stop():
    ena.value = 0
    enb.value = 0

    in1.off()
    in2.off()
    in3.off()
    in4.off()


def forward():
    in1.on()
    in2.off()
    in3.on()
    in4.off()

    ena.value = FORWARD_SPEED
    enb.value = FORWARD_SPEED


def left():
    # Rotate left
    in1.off()
    in2.on()
    in3.on()
    in4.off()

    ena.value = TURN_SPEED
    enb.value = TURN_SPEED


def right():
    # Rotate right
    in1.on()
    in2.off()
    in3.off()
    in4.on()

    ena.value = TURN_SPEED
    enb.value = TURN_SPEED


try:
    stop()

    print("\n=== SMART TROLLEY MOTOR CONTROL ===")
    print("f = Forward")
    print("l = Turn left")
    print("r = Turn right")
    print("s = Stop")
    print("q = Quit")

    while True:
        command = input("\nEnter command: ").strip().lower()

        if command == "f":
            forward()
            print("Moving FORWARD at 40% speed")

        elif command == "l":
            left()
            print("Turning LEFT at 30% speed")

        elif command == "r":
            right()
            print("Turning RIGHT at 30% speed")

        elif command == "s":
            stop()
            print("STOPPED")

        elif command == "q":
            stop()
            print("Exiting motor controller")
            break

        else:
            print("Invalid command. Use f, l, r, s, or q.")

except KeyboardInterrupt:
    print("\nInterrupted")

finally:
    stop()

    for device in (ena, enb, in1, in2, in3, in4):
        device.close()

    print("All motor outputs disabled.")
