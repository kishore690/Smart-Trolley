
from gpiozero import DigitalOutputDevice
from time import sleep

# BCM GPIO pin numbers
ENA = 18
IN1 = 17
IN2 = 27
IN3 = 22
IN4 = 23
ENB = 24

pins = [ENA, IN1, IN2, IN3, IN4, ENB]
devices = []

try:
    for pin in pins:
        devices.append(
            DigitalOutputDevice(
                pin, initial_value=False
            )
        )

    print("GPIO initialized successfully.")
    print("All motor signals are LOW.")
    print("Motors should remain stopped.")

    while True:
        sleep(1)

except KeyboardInterrupt:
    print("\nTest stopped.")

finally:
    for device in devices:
        device.off()
        device.close()

    print("GPIO outputs set LOW.")
