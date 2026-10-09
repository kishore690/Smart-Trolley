
import time
from pathlib import Path

import cv2
from ultralytics import YOLO

MODEL_PATH = "yolov8n.pt"
COMMAND_FILE = Path(__file__).with_name("motor_command.txt")

CAMERA_INDEX = 0
IMAGE_SIZE = 320
CONFIDENCE = 0.40

# Follow closer using the person's detected height in the image.
FOLLOW_RATIO = 0.35
TOO_CLOSE_RATIO = 0.50

# Horizontal position thresholds.
LEFT_LIMIT = 0.40
RIGHT_LIMIT = 0.60

# Stop if the target is missing for this long.
LOST_TIMEOUT = 1.0

# Require repeated likely-obstacle detections to reduce false stops.
OBSTACLE_CONFIDENCE = 0.70
OBSTACLE_FRAMES_REQUIRED = 4


def send_command(command):
    try:
        COMMAND_FILE.write_text(command + "\n")
    except OSError as exc:
        print(f"COMMAND FILE ERROR: {exc}", flush=True)


camera = None

try:
    send_command("STOP")

    print("Loading YOLOv8n...", flush=True)
    model = YOLO(MODEL_PATH)

    camera = cv2.VideoCapture(CAMERA_INDEX)
    if not camera.isOpened():
        raise RuntimeError("Cannot open webcam")

    camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    last_person_seen = time.time()
    obstacle_frames = 0

    print("Camera following started.", flush=True)
    print("Keep yourself clearly visible in the camera.", flush=True)
    print("Press Ctrl+C to stop.", flush=True)

    while True:
        ok, frame = camera.read()

        if not ok:
            send_command("STOP")
            print("CAMERA ERROR -> STOP", flush=True)
            time.sleep(0.2)
            continue

        result = model.predict(
            frame,
            imgsz=IMAGE_SIZE,
            conf=CONFIDENCE,
            device="cpu",
            verbose=False
        )[0]

        h, w = frame.shape[:2]
        people = []
        possible_obstacle = False

        if result.boxes is not None:
            for box in result.boxes:
                cls = int(box.cls[0].item())
                conf = float(box.conf[0].item())

                x1, y1, x2, y2 = map(
                    int, box.xyxy[0].tolist()
                )

                cx = (x1 + x2) // 2
                cy = (y1 + y2) // 2
                box_width = x2 - x1
                box_height = y2 - y1
                height_ratio = box_height / h

                if cls == 0:
                    people.append({
                        "cx": cx,
                        "ratio": height_ratio,
                        "confidence": conf
                    })

                # Heuristic only; it cannot guarantee collision avoidance.
                elif (
                    conf >= OBSTACLE_CONFIDENCE
                    and w * 0.25 < cx < w * 0.75
                    and cy > h * 0.45
                    and box_width > w * 0.08
                    and box_height > h * 0.08
                ):
                    possible_obstacle = True

        if possible_obstacle:
            obstacle_frames += 1
        else:
            obstacle_frames = 0

        obstacle_detected = (
            obstacle_frames >= OBSTACLE_FRAMES_REQUIRED
        )

        command = "STOP"
        reason = "NO_PERSON_DETECTED"

        if obstacle_detected:
            reason = "POSSIBLE_OBSTACLE"

        elif people:
            # Follow the largest visible person.
            # Keep other people out of view to avoid switching targets.
            person = max(people, key=lambda p: p["ratio"])
            cx = person["cx"]
            ratio = person["ratio"]

            last_person_seen = time.time()

            if ratio >= TOO_CLOSE_RATIO:
                reason = "TOO_CLOSE"

            elif cx < w * LEFT_LIMIT:
                command = "LEFT"
                reason = "PERSON_LEFT"

            elif cx > w * RIGHT_LIMIT:
                command = "RIGHT"
                reason = "PERSON_RIGHT"

            elif ratio < FOLLOW_RATIO:
                command = "FORWARD"
                reason = "PERSON_CENTERED_FAR"

            else:
                reason = "FOLLOW_DISTANCE_REACHED"

            print(
                f"CenterX={cx}/{w} "
                f"HeightRatio={ratio:.3f} "
                f"Confidence={person['confidence']:.2f}",
                flush=True
            )

        else:
            if time.time() - last_person_seen > LOST_TIMEOUT:
                reason = "PERSON_LOST_STOP"
            else:
                reason = "PERSON_TEMPORARILY_MISSING"

        send_command(command)

        print(
            f"People={len(people)} "
            f"Obstacle={obstacle_detected} "
            f"Command={command} Reason={reason}",
            flush=True
        )

except KeyboardInterrupt:
    print("\nStopping camera follow...", flush=True)

except Exception as exc:
    print(f"ERROR: {exc}", flush=True)

finally:
    send_command("STOP")

    if camera is not None:
        camera.release()

    print("STOP command sent; camera released.", flush=True)
