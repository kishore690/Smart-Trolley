
import cv2
import time
from ultralytics import YOLO

# Configuration
MODEL_PATH = "yolov8n.pt"
CAMERA_INDEX = 0
IMAGE_SIZE = 320
CONFIDENCE = 0.35

# Central region used for this initial test
CENTER_X_MIN = 0.25
CENTER_X_MAX = 0.75
CENTER_Y_MIN = 0.20
CENTER_Y_MAX = 0.90

print("Loading YOLOv8n...", flush=True)
model = YOLO(MODEL_PATH)

camera = cv2.VideoCapture(CAMERA_INDEX)

if not camera.isOpened():
    raise RuntimeError("Webcam unavailable")

camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

print("\n=== GENERAL OBSTACLE DETECTION TEST ===")
print("All detected non-person objects are potential obstacles.")
print("Person detections are ignored in this standalone test.")
print("Central obstacle detected -> STOP.")
print("No motor commands are sent.")
print("Press Ctrl+C to stop.\n")

try:
    while True:
        success, frame = camera.read()

        if not success:
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

        height, width = frame.shape[:2]

        detected_objects = []
        central_obstacles = []

        if result.boxes is not None:
            for i in range(len(result.boxes)):
                box = result.boxes[i]

                class_id = int(box.cls[0])
                label = result.names[class_id]

                # Ignore person detections in this standalone test.
                if label == "person":
                    continue

                x1, y1, x2, y2 = map(
                    int, box.xyxy[0].tolist()
                )

                center_x = (x1 + x2) / 2
                center_y = (y1 + y2) / 2

                detected_objects.append(label)

                # Check whether the object is in the central region.
                in_center = (
                    CENTER_X_MIN * width <= center_x
                    <= CENTER_X_MAX * width
                    and CENTER_Y_MIN * height <= center_y
                    <= CENTER_Y_MAX * height
                )

                if in_center:
                    central_obstacles.append(label)

        if central_obstacles:
            command = "STOP"
            status = "OBSTACLE DETECTED"
        else:
            command = "NO_STOP_REQUEST"
            status = "NO RECOGNIZED CENTRAL OBSTACLE"

        print(
            f"Objects={sorted(set(detected_objects))} | "
            f"CentralObstacles={sorted(set(central_obstacles))} | "
            f"Status={status} | Decision={command}",
            flush=True
        )

except KeyboardInterrupt:
    print("\nTest stopped by user.")

finally:
    camera.release()
    print("Camera released. Motors were not controlled.")
