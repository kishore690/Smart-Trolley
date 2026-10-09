
import time
import cv2
from gpiozero import Device, DigitalOutputDevice, PWMOutputDevice
from gpiozero.pins.lgpio import LGPIOFactory
from ultralytics import YOLO

# Select LGPIO before initializing any GPIO devices
Device.pin_factory = LGPIOFactory()

# Motor GPIO pins (BCM numbering)
ENA, IN1, IN2 = 18, 17, 27
ENB, IN3, IN4 = 24, 22, 23

MODEL_PATH = "yolov8n.pt"
CAMERA_INDEX = 0
IMAGE_SIZE = 320
CONFIDENCE = 0.50
SELECTION_SECONDS = 5
LOST_TIMEOUT = 1.0

# Conservative initial motor speed
SPEED = 0.25
TURN_SPEED = 0.20

ena = enb = None
in1 = in2 = in3 = in4 = None
camera = None

def stop():
    if ena:
        ena.value = 0
    if enb:
        enb.value = 0
    for motor_pin in (in1, in2, in3, in4):
        if motor_pin:
            motor_pin.off()

def forward():
    in1.on()
    in2.off()
    in3.on()
    in4.off()
    ena.value = SPEED
    enb.value = SPEED

def left():
    in1.off()
    in2.on()
    in3.on()
    in4.off()
    ena.value = TURN_SPEED
    enb.value = TURN_SPEED

def right():
    in1.on()
    in2.off()
    in3.off()
    in4.on()
    ena.value = TURN_SPEED
    enb.value = TURN_SPEED

try:
    # Initialize outputs LOW
    ena = PWMOutputDevice(ENA, initial_value=0)
    enb = PWMOutputDevice(ENB, initial_value=0)
    in1 = DigitalOutputDevice(IN1, initial_value=False)
    in2 = DigitalOutputDevice(IN2, initial_value=False)
    in3 = DigitalOutputDevice(IN3, initial_value=False)
    in4 = DigitalOutputDevice(IN4, initial_value=False)
    stop()

    print("Loading YOLOv8n...", flush=True)
    model = YOLO(MODEL_PATH)

    camera = cv2.VideoCapture(CAMERA_INDEX)
    if not camera.isOpened():
        raise RuntimeError("Webcam unavailable")

    camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    print("Target selection starts now.")
    print("Stand alone in view for 5 seconds.")
    print("Press Q in the camera window or Ctrl+C to stop.")

    selection_deadline = time.time() + SELECTION_SECONDS
    target_id = None
    last_seen = None
    locked_out = False

    while True:
        ok, frame = camera.read()
        if not ok:
            stop()
            print("CAMERA ERROR -> STOP")
            break

        now = time.time()

        result = model.track(
            frame,
            persist=True,
            tracker="bytetrack.yaml",
            imgsz=IMAGE_SIZE,
            conf=CONFIDENCE,
            device="cpu",
            verbose=False
        )[0]

        h, w = frame.shape[:2]
        people = []

        if result.boxes is not None:
            boxes = result.boxes

            for i in range(len(boxes)):
                if int(boxes.cls[i].item()) != 0:
                    continue

                if boxes.id is None:
                    continue

                x1, y1, x2, y2 = map(
                    int, boxes.xyxy[i].tolist()
                )
                people.append({
                    "id": int(boxes.id[i].item()),
                    "cx": (x1 + x2) // 2,
                    "height_ratio": (y2 - y1) / h,
                    "bbox": (x1, y1, x2, y2)
                })

        # Select the largest visible person during startup
        if (
            target_id is None
            and now <= selection_deadline
            and people
        ):
            selected = max(
                people, key=lambda p: p["height_ratio"]
            )
            target_id = selected["id"]
            last_seen = now
            print(f"TARGET SELECTED: {target_id}")

        target = next(
            (p for p in people if p["id"] == target_id),
            None
        ) if target_id is not None else None

        command = "STOP"

        if locked_out:
            command = "STOP"

        elif target is not None:
            last_seen = now
            ratio = target["height_ratio"]
            cx = target["cx"]

            if now < selection_deadline:
                command = "STOP"
            elif ratio >= 0.40:
                command = "STOP"
            elif cx < w * 0.40:
                command = "TURN_LEFT"
            elif cx > w * 0.60:
                command = "TURN_RIGHT"
            elif ratio < 0.30:
                command = "FORWARD"
            else:
                command = "STOP"

        elif target_id is not None:
            if last_seen is None or now - last_seen >= LOST_TIMEOUT:
                locked_out = True
                print("TARGET LOST -> STOP. Restart to select again.")

        elif now > selection_deadline:
            print("NO TARGET SELECTED -> STOP")
            break

        # Apply a fresh command each frame
        stop()

        if command == "FORWARD":
            forward()
        elif command == "TURN_LEFT":
            left()
        elif command == "TURN_RIGHT":
            right()

        for p in people:
            x1, y1, x2, y2 = p["bbox"]
            cv2.rectangle(
                frame, (x1, y1), (x2, y2), (0, 255, 0), 2
            )

        cv2.putText(
            frame, f"Command: {command}",
            (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
            0.7, (255, 255, 0), 2
        )
        cv2.imshow("Smart Trolley", frame)

        print(
            f"People={len(people)} Target={target_id} "
            f"Command={command} LockedOut={locked_out}",
            flush=True
        )

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

except KeyboardInterrupt:
    print("\nStopping...")

finally:
    stop()

    if camera is not None:
        camera.release()

    cv2.destroyAllWindows()

    for device in (ena, enb, in1, in2, in3, in4):
        if device is not None:
            device.close()

    print("Motor outputs disabled.")
