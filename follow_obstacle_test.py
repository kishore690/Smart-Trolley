
import cv2
import time
from ultralytics import YOLO

# ---------------- CONFIGURATION ----------------

MODEL_PATH = "yolov8n.pt"
CAMERA_INDEX = 0
IMAGE_SIZE = 320
CONFIDENCE = 0.45
SELECTION_SECONDS = 5
LOST_TIMEOUT = 1.5

# Recognized objects that may indicate an obstacle.
# This list is not exhaustive and is only for testing.
OBSTACLE_CLASSES = {
    "bicycle", "car", "motorcycle", "bus", "truck",
    "bench", "chair", "couch", "potted plant",
    "suitcase", "backpack", "handbag", "dog", "cat",
    "bottle", "cup", "umbrella", "sports ball",
    "skateboard"
}

# ---------------- INITIALIZATION ----------------

print("Loading YOLOv8n...", flush=True)
model = YOLO(MODEL_PATH)

camera = cv2.VideoCapture(CAMERA_INDEX)

if not camera.isOpened():
    raise RuntimeError("Webcam unavailable")

camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

target_id = None
selection_deadline = time.time() + SELECTION_SECONDS
last_seen = None
target_locked_out = False

print("\n=== PERSON + OBSTACLE DECISION TEST ===")
print("Stand alone in view during the first 5 seconds.")
print("A detected central obstacle forces STOP.")
print("Target lost for 1.5 seconds causes permanent STOP lockout.")
print("Restart the program to select a target again.")
print("NO MOTOR COMMANDS WILL BE SENT.\n")

# ---------------- MAIN LOOP ----------------

try:
    while True:
        success, frame = camera.read()

        if not success:
            print("CAMERA ERROR -> STOP", flush=True)
            time.sleep(0.2)
            continue

        now = time.time()

        # Detect and track objects
        result = model.track(
            frame,
            persist=True,
            tracker="bytetrack.yaml",
            imgsz=IMAGE_SIZE,
            conf=CONFIDENCE,
            device="cpu",
            verbose=False
        )[0]

        frame_height, frame_width = frame.shape[:2]

        people = []
        central_obstacle = False
        obstacle_names = []

        # Process detections by index
        if result.boxes is not None:
            boxes = result.boxes
            names = result.names

            track_ids = None

            if boxes.id is not None:
                track_ids = boxes.id.int().cpu().tolist()

            for i in range(len(boxes)):
                box = boxes[i]

                class_id = int(box.cls[0])
                label = names[class_id]

                x1, y1, x2, y2 = map(
                    int, box.xyxy[0].tolist()
                )

                center_x = (x1 + x2) // 2
                center_y = (y1 + y2) // 2

                # Collect tracked people
                if label == "person" and track_ids is not None:
                    people.append({
                        "id": track_ids[i],
                        "bbox": (x1, y1, x2, y2),
                        "center_x": center_x,
                        "height": y2 - y1
                    })

                # Check recognized non-person objects
                if label in OBSTACLE_CLASSES:
                    in_center_zone = (
                        frame_width * 0.25 <= center_x
                        <= frame_width * 0.75
                        and frame_height * 0.20 <= center_y
                        <= frame_height * 0.90
                    )

                    if in_center_zone:
                        central_obstacle = True
                        obstacle_names.append(label)

        # Select the largest person during the initial window
        if (
            target_id is None
            and now <= selection_deadline
            and people
        ):
            selected = max(people, key=lambda p: p["height"])
            target_id = selected["id"]
            last_seen = now

            print(f"TARGET LOCKED: ID {target_id}", flush=True)

        # Find only the selected track
        target = None

        if target_id is not None:
            target = next(
                (p for p in people if p["id"] == target_id),
                None
            )

        command = "STOP"

        # Priority 1: permanent stop after target loss
        if target_locked_out:
            command = "STOP"

        # Priority 2: missing selected target
        elif target_id is not None and target is None:
            command = "STOP"

            if (
                last_seen is not None
                and now - last_seen >= LOST_TIMEOUT
            ):
                target_locked_out = True

                print(
                    f"TARGET {target_id} LOST -> STOP LOCKED. "
                    "Restart to select a target again.",
                    flush=True
                )

        # Selected target is visible
        elif target is not None:
            last_seen = now

            # Priority 3: recognized central obstacle
            if central_obstacle:
                command = "STOP"

            # Wait until the selection period ends
            elif now < selection_deadline:
                command = "STOP"

            else:
                center_x = target["center_x"]
                height_ratio = (
                    target["height"] / frame_height
                )

                if height_ratio >= 0.80:
                    command = "STOP"

                elif center_x < frame_width * 0.40:
                    command = "TURN_LEFT"

                elif center_x > frame_width * 0.60:
                    command = "TURN_RIGHT"

                elif height_ratio < 0.60:
                    command = "FORWARD"

                else:
                    command = "STOP"

        # No target was found during selection
        elif now > selection_deadline and target_id is None:
            print(
                "NO TARGET SELECTED -> STOP. "
                "Restart and stand clearly in view.",
                flush=True
            )
            break

        # Status output
        obstacle_text = (
            ",".join(sorted(set(obstacle_names)))
            if central_obstacle else "none"
        )

        print(
            f"People={len(people)} | "
            f"Target={target_id} | "
            f"Obstacle={obstacle_text} | "
            f"Command={command} | "
            f"LockedOut={target_locked_out}",
            flush=True
        )

except KeyboardInterrupt:
    print("\nTest stopped by user.")

finally:
    camera.release()
    print("Camera released. Motors were not controlled.")
