
import cv2
import time
from ultralytics import YOLO

# Configuration
MODEL_PATH = "yolov8n.pt"
CAMERA_INDEX = 0
IMAGE_SIZE = 320
CONFIDENCE = 0.5
SELECTION_SECONDS = 5
LOST_TIMEOUT = 1.5

# Load YOLO model
print("Loading YOLOv8n...", flush=True)
model = YOLO(MODEL_PATH)

# Open webcam
camera = cv2.VideoCapture(CAMERA_INDEX)

if not camera.isOpened():
    raise RuntimeError("Webcam unavailable")

camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

# Tracking state
target_id = None
selection_deadline = time.time() + SELECTION_SECONDS
last_seen = None
target_locked_out = False

print("\n=== TARGET LOCK TEST ===")
print("Stand alone in front of the camera for 5 seconds.")
print("The largest detected person will be selected.")
print("If the target is lost, STOP remains locked.")
print("Restart the program to select a new target.")
print("IMPORTANT: This program does NOT control motors.\n")

try:
    while True:
        success, frame = camera.read()

        if not success:
            print("CAMERA ERROR -> STOP", flush=True)
            time.sleep(0.2)
            continue

        now = time.time()

        # Detect and track people
        result = model.track(
            frame,
            persist=True,
            tracker="bytetrack.yaml",
            imgsz=IMAGE_SIZE,
            conf=CONFIDENCE,
            device="cpu",
            verbose=False
        )[0]

        people = []

        if result.boxes is not None and result.boxes.id is not None:
            boxes = result.boxes
            track_ids = boxes.id.int().cpu().tolist()

            for box, track_id in zip(boxes, track_ids):
                # YOLO class 0 = person
                if int(box.cls[0]) != 0:
                    continue

                x1, y1, x2, y2 = map(
                    int, box.xyxy[0].tolist()
                )

                people.append({
                    "id": track_id,
                    "bbox": (x1, y1, x2, y2),
                    "center_x": (x1 + x2) // 2,
                    "height": y2 - y1
                })

        # Select the largest person during initial selection window
        if (
            target_id is None
            and now <= selection_deadline
            and people
        ):
            selected = max(people, key=lambda person: person["height"])
            target_id = selected["id"]
            last_seen = now

            print(f"TARGET LOCKED: ID {target_id}", flush=True)

        # Find only the selected target
        target = None

        if target_id is not None:
            target = next(
                (person for person in people
                 if person["id"] == target_id),
                None
            )

        command = "STOP"

        # Once locked out, NEVER resume movement in this run
        if target_locked_out:
            command = "STOP"

        # Selected target is visible and not locked out
        elif target is not None:
            last_seen = now

            frame_height, frame_width = frame.shape[:2]
            center_x = target["center_x"]
            height_ratio = target["height"] / frame_height

            if now < selection_deadline:
                command = "STOP"

            # Too close to camera
            elif height_ratio >= 0.80:
                command = "STOP"

            # Target is to the left
            elif center_x < frame_width * 0.40:
                command = "TURN_LEFT"

            # Target is to the right
            elif center_x > frame_width * 0.60:
                command = "TURN_RIGHT"

            # Target is centered and appears far away
            elif height_ratio < 0.60:
                command = "FORWARD"

            # Target is close enough
            else:
                command = "STOP"

        # Target is missing
        elif target_id is not None:
            command = "STOP"

            if (
                last_seen is not None
                and now - last_seen >= LOST_TIMEOUT
            ):
                target_locked_out = True

                print(
                    f"TARGET {target_id} LOST -> STOP.\n"
                    "Following is locked out. Restart the program "
                    "to select a target again.",
                    flush=True
                )

        # Selection window expired without finding a person
        elif now > selection_deadline:
            print(
                "NO TARGET SELECTED -> STOP. "
                "Restart and stand clearly in view.",
                flush=True
            )
            break

        else:
            command = "STOP"

        # Print status periodically for debugging
        print(
            f"People={len(people)} | "
            f"Target={target_id} | "
            f"Command={command} | "
            f"LockedOut={target_locked_out}",
            flush=True
        )

except KeyboardInterrupt:
    print("\nTracker stopped by user.")

finally:
    camera.release()
    print("Camera released. Motors were not controlled.")
