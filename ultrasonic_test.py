
from gpiozero import DistanceSensor
from statistics import median
from time import sleep

TRIG = 5
ECHO = 6

sensor = DistanceSensor(
    echo=ECHO,
    trigger=TRIG,
    max_distance=3.0,
    queue_len=5,
    threshold_distance=0.2
)

try:
    print("Ultrasonic test: median-filtered readings")
    print("Keep a flat object 20-30 cm in front.")
    print("Press Ctrl+C to stop.\n")

    while True:
        readings = []

        for _ in range(5):
            d = sensor.distance * 100

            # Ignore maximum-range/no-echo readings
            if 2.0 <= d < 290.0:
                readings.append(d)

            sleep(0.08)

        if len(readings) >= 3:
            print(f"Distance: {median(readings):.1f} cm")
        else:
            print("Unreliable/no echo - treat as unsafe")

        sleep(0.2)

except KeyboardInterrupt:
    print("\nTest stopped.")

finally:
    sensor.close()
