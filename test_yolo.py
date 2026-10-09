import cv2
from ultralytics import YOLO

print("Loading YOLOv8n...", flush=True)
model = YOLO("yolov8n.pt")

print("Opening webcam...", flush=True)
camera = cv2.VideoCapture(0)

if not camera.isOpened():
    print("ERROR: Webcam not available")
    raise SystemExit(1)

camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

try:
    print("Capturing webcam frame...", flush=True)

    success, frame = camera.read()

    if not success:
        print("ERROR: Could not capture frame")
        raise SystemExit(1)

    print("Running YOLO inference...", flush=True)

    results = model.predict(
        frame,
        imgsz=320,
        device="cpu",
        conf=0.5,
        verbose=False
    )

    people = [
        box for box in results[0].boxes
        if int(box.cls[0]) == 0
    ]

    print(f"People detected: {len(people)}", flush=True)

    annotated = results[0].plot()
    cv2.imwrite("person_detection.jpg", annotated)

    print("Saved: person_detection.jpg", flush=True)

finally:
    camera.release()
