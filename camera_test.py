import cv2

camera = cv2.VideoCapture(0)

if not camera.isOpened():
    print("ERROR: Could not open webcam")
    exit()

ret, frame = camera.read()

if ret:
    cv2.imwrite("camera_test.jpg", frame)
    print("SUCCESS: Camera frame captured")
    print("Saved as camera_test.jpg")
else:
    print("ERROR: Could not read frame")

camera.release()
