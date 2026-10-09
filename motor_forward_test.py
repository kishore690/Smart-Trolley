
from gpiozero import DigitalOutputDevice, PWMOutputDevice
from time import sleep

# Raspberry Pi BCM GPIO numbers
ENA = 18
IN1 = 17
IN2 = 27
IN3 = 22
IN4 = 23
ENB = 24

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

try:
    print("Motors stopped.")
    input("Lift wheels and connect motor battery, then press Enter...")

    # Brief forward test at 35% speed
    print("Moving forward for 1 second...")
    in1.on()
    in2.off()
    in3.on()
    in4.off()
    ena.value = 0.35
    enb.value = 0.35
    sleep(1)

    stop()
    print("STOP: test completed.")

except KeyboardInterrupt:
    print("\nEmergency stop requested.")

finally:
    stop()
    ena.close()
    enb.close()
    in1.close()
    in2.close()
    in3.close()
    in4.close()
    print("Motor outputs disabled.")
