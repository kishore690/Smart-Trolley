"""Human-following drive loop for the Smart Trolley Raspberry Pi.

Fail-safe defaults: motors remain stopped until the camera, person model, motor
GPIO, and HC-SR04 all initialize. ECHO must be connected through a divider.
This is a supervised prototype, not a substitute for a physical emergency stop.
"""

from __future__ import annotations

import logging
import os
import signal
import time
from dataclasses import dataclass

import cv2
from gpiozero import DigitalOutputDevice, DistanceSensor
from ultralytics import YOLO


LOG = logging.getLogger("smart_trolley.follow")


@dataclass(frozen=True)
class Config:
    # BCM numbering; these match the pin plan already supplied by the user.
    left_a: int = 17
    left_b: int = 27
    right_a: int = 22
    right_b: int = 23
    # Set these only after wiring is confirmed. ECHO needs a resistor divider.
    trigger: int = int(os.environ.get("TROLLEY_HCSR04_TRIGGER", "-1"))
    echo: int = int(os.environ.get("TROLLEY_HCSR04_ECHO", "-1"))
    camera_index: int = int(os.environ.get("TROLLEY_CAMERA_INDEX", "0"))
    model_path: str = os.environ.get("TROLLEY_PERSON_MODEL", "yolo26n_ncnn_model")
    obstacle_stop_m: float = 0.40
    target_box_height: float = 0.22
    align_tolerance: float = 0.14
    inference_size: int = 320
    control_period_s: float = 0.20
    # A short pulse limits uncontrolled motion while using the L298N jumpers.
    motor_pulse_s: float = 0.12


class Drive:
    """Two L298N channels, one channel per trolley side, ENA/ENB jumpered."""

    def __init__(self, cfg: Config):
        self.left_a = DigitalOutputDevice(cfg.left_a, initial_value=False)
        self.left_b = DigitalOutputDevice(cfg.left_b, initial_value=False)
        self.right_a = DigitalOutputDevice(cfg.right_a, initial_value=False)
        self.right_b = DigitalOutputDevice(cfg.right_b, initial_value=False)
        self.stop()

    def stop(self) -> None:
        for pin in (self.left_a, self.left_b, self.right_a, self.right_b):
            pin.off()

    def forward(self) -> None:
        self.left_a.on()
        self.left_b.off()
        self.right_a.on()
        self.right_b.off()

    def turn_left(self) -> None:
        self.left_a.off()
        self.left_b.on()
        self.right_a.on()
        self.right_b.off()

    def turn_right(self) -> None:
        self.left_a.on()
        self.left_b.off()
        self.right_a.off()
        self.right_b.on()

    def close(self) -> None:
        self.stop()
        for pin in (self.left_a, self.left_b, self.right_a, self.right_b):
            pin.close()


def best_person(model: YOLO, frame):
    """Return normalized center-x and height for the largest detected person."""
    height, width = frame.shape[:2]
    result = model.predict(
        frame,
        imgsz=Config.inference_size,
        classes=[0],
        conf=0.45,
        verbose=False,
        device="cpu",
    )[0]
    if result.boxes is None or len(result.boxes) == 0:
        return None
    boxes = result.boxes.xyxy.cpu().numpy()
    scores = result.boxes.conf.cpu().numpy()
    index = max(range(len(boxes)), key=lambda i: float(scores[i]))
    x1, y1, x2, y2 = boxes[index]
    return ((float(x1 + x2) / 2) / width, max(0.0, float(y2 - y1) / height))


def main() -> None:
    if not os.environ.get("TROLLEY_HCSR04_TRIGGER") or not os.environ.get("TROLLEY_HCSR04_ECHO"):
        raise SystemExit(
            "Refusing to start: set TROLLEY_HCSR04_TRIGGER and TROLLEY_HCSR04_ECHO "
            "to the confirmed BCM GPIO pins after wiring the ECHO voltage divider."
        )

    cfg = Config()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    drive = None
    camera = None
    distance = None
    running = True

    def request_stop(_signum, _frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    try:
        # Initialize sensors and model before constructing the motor outputs.
        distance = DistanceSensor(
            echo=cfg.echo,
            trigger=cfg.trigger,
            max_distance=2.0,
            threshold_distance=cfg.obstacle_stop_m,
        )
        camera = cv2.VideoCapture(cfg.camera_index, cv2.CAP_V4L2)
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        if not camera.isOpened():
            raise RuntimeError(f"Could not open USB camera index {cfg.camera_index}")
        model = YOLO(cfg.model_path)
        drive = Drive(cfg)
        LOG.info("Follow controller ready; press Ctrl+C to stop")

        while running:
            started = time.monotonic()
            ok, frame = camera.read()
            if not ok:
                drive.stop()
                LOG.warning("Camera frame unavailable; stopped")
                time.sleep(cfg.control_period_s)
                continue

            # Sensor read exceptions propagate to the cleanup path, which stops motors.
            obstacle_m = distance.distance
            person = best_person(model, frame)
            if obstacle_m <= cfg.obstacle_stop_m:
                drive.stop()
                LOG.info("Obstacle at %.2f m; stopped", obstacle_m)
            elif person is None:
                drive.stop()
                LOG.info("Person not detected; stopped")
            else:
                center_x, box_height = person
                error = center_x - 0.5
                if error < -cfg.align_tolerance:
                    drive.turn_left()
                elif error > cfg.align_tolerance:
                    drive.turn_right()
                elif box_height < cfg.target_box_height:
                    drive.forward()
                else:
                    drive.stop()
                LOG.info(
                    "person_x=%.2f box_h=%.2f distance=%.2fm action=%s",
                    center_x,
                    box_height,
                    obstacle_m,
                    "left" if error < -cfg.align_tolerance else
                    "right" if error > cfg.align_tolerance else
                    "forward" if box_height < cfg.target_box_height else "stop",
                )

            # With EN jumpers installed the driver has no speed control. Use brief
            # movement pulses, then coast while the next frame/sensor reading is taken.
            time.sleep(cfg.motor_pulse_s)
            drive.stop()
            elapsed = time.monotonic() - started
            time.sleep(max(0.0, cfg.control_period_s - elapsed - cfg.motor_pulse_s))
    finally:
        if drive is not None:
            drive.close()
        if camera is not None:
            camera.release()
        if distance is not None:
            distance.close()
        LOG.info("Controller stopped; outputs released")


if __name__ == "__main__":
    main()
