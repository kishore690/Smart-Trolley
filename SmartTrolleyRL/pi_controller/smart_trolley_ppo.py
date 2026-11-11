import glob
import json
import math
import os
import queue
import select
import threading
import time
import uuid
from datetime import datetime, timedelta

import cv2
import numpy as np
import onnxruntime as ort
import RPi.GPIO as GPIO
from evdev import InputDevice, ecodes
from mfrc522 import SimpleMFRC522
from RPLCD.i2c import CharLCD


# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = "/home/kishore/smart-trolley"
MODEL_PATH = f"{BASE_DIR}/yolov8n.onnx"
PPO_MODEL_PATH = os.environ.get(
    "TROLLEY_PPO_MODEL",
    "/home/kishore/SmartTrolleyRL/models/ppo_trolley.onnx"
)

CAMERA_INDEX = 0

AUTHORIZED_CARDS = {995728951076}

SESSION_PRICE_RUPEES = 20
SESSION_MINUTES = 30

# L298N pins (BCM numbering)
IN1 = 17
IN2 = 27
IN3 = 22
IN4 = 23

ENA = 18
ENB = 19

# Motor direction correction
REVERSE_LEFT_MOTOR = False
REVERSE_RIGHT_MOTOR = False

# Motor speeds
MOTOR_CONTROL_ENABLED = True
FORWARD_SPEED = 100
TURN_SPEED = 50

motor_pwm_left = None
motor_pwm_right = None

# AI settings
INPUT_SIZE = 640
CONFIDENCE_THRESHOLD = 0.45
NMS_THRESHOLD = 0.45

# Must be calibrated for the actual camera; PPO was trained with metric ranges.
CAMERA_FOCAL_Y_PX = float(os.environ.get("TROLLEY_FOCAL_Y_PX", "500.0"))
CAMERA_HORIZONTAL_FOV_DEG = float(os.environ.get("TROLLEY_HORIZONTAL_FOV_DEG", "69.0"))
MAX_LINEAR_SPEED_MPS = 0.25
MAX_TURN_RATE_RADPS = 0.65
MIN_FOLLOW_DISTANCE_M = 0.70
OBSTACLE_STOP_DISTANCE_M = 0.55
OBSTACLE_SLOW_DISTANCE_M = 1.0
UNKNOWN_RANGE_SPEED_MPS = 0.16
UNKNOWN_RANGE_TURN_RADPS = 0.30
VISION_UNKNOWN_RANGE_M = 8.0
WHEEL_TRACK_M = 0.52
MAX_WHEEL_SPEED_MPS = 0.45

HAZARD_CLASS_HEIGHTS = {
    56: 0.9, 57: 0.9, 58: 0.8, 59: 0.55, 60: 0.75,
    61: 0.75, 68: 0.35, 69: 0.9, 71: 0.9, 72: 1.7,
}

LOCK_SECONDS = 5.0
TARGET_LOST_SECONDS = 1.0

CENTER_DEAD_ZONE = 0.12

FOLLOW_MIN_HEIGHT = 0.18
STOP_MIN_HEIGHT = 0.48

# LCD
LCD_ADDRESS = 0x27

# Barcode scanner
BARCODE_DEVICE_GLOB = (
    "/dev/input/by-id/*event-kbd"
)
BARCODE_DUPLICATE_GUARD_SECONDS = 0.35

# Product catalogue
DEFAULT_PRODUCTS = {
    "8901234567890": {
        "name": "Sample Biscuit",
        "price": 20.0
    },

    "8901234567891": {
        "name": "Sample Chips",
        "price": 30.0
    }
}
PRODUCTS = dict(DEFAULT_PRODUCTS)


# ============================================================
# SHARED VARIABLES
# ============================================================

barcode_queue = queue.Queue()

barcode_stop = threading.Event()
barcode_thread = None

cart = {}
cart_lock = threading.Lock()

lcd = None
reader = None

onnx_session = None
input_name = None
ppo_session = None
ppo_input_name = None
ppo_previous_action = np.zeros(2, dtype=np.float32)
previous_linear_velocity = 0.0
previous_angular_velocity = 0.0
current_obstacle_distances = [None, None, None]

# Cartly customer app API state. The API reads the same session/cart used by this
# trolley process; the only write action exposed is an explicit checkout request.
API_HOST = os.environ.get("TROLLEY_API_HOST", "0.0.0.0")
API_PORT = int(os.environ.get("TROLLEY_API_PORT", "8000"))
api_state_lock = threading.RLock()
active_session_state = None
latest_scan_state = None
camera_active = False
barcode_scanner_active = False
api_server_thread = None
checkout_requested = threading.Event()
session_finished = threading.Event()
authorized_card_id = None


def load_product_catalogue():
    """Load exhibition product data from ~/smart-trolley/products.json."""
    global PRODUCTS
    path = os.environ.get("TROLLEY_PRODUCTS_FILE", f"{BASE_DIR}/products.json")
    if not os.path.isfile(path):
        PRODUCTS = dict(DEFAULT_PRODUCTS)
        print(f"[CATALOGUE] {path} not found; using built-in sample products ({len(PRODUCTS)}).")
        return

    with open(path, "r", encoding="utf-8") as file:
        raw = json.load(file)
    if not isinstance(raw, dict) or not raw:
        raise ValueError(f"Product catalogue {path} must be a non-empty JSON object keyed by barcode")

    products = {}
    for barcode, item in raw.items():
        barcode = str(barcode).strip()
        if not barcode or not barcode.isdigit():
            raise ValueError(f"Invalid barcode {barcode!r} in {path}; use digits only")
        if not isinstance(item, dict) or not str(item.get("name", "")).strip():
            raise ValueError(f"Product {barcode} needs a non-empty name")
        try:
            price = float(item["price"])
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"Product {barcode} needs a numeric price")
        if not math.isfinite(price) or price < 0:
            raise ValueError(f"Product {barcode} price must be a finite non-negative number")
        products[barcode] = {"name": str(item["name"]).strip(), "price": price}

    PRODUCTS = products
    print(f"[CATALOGUE] Loaded {len(PRODUCTS)} products from {path}.")


def cart_snapshot():
    with cart_lock:
        items = [
            {
                "product_id": barcode,
                "barcode": barcode,
                "name": item["name"],
                "quantity": item["quantity"],
                "unit_price": item["price"],
                "line_total": item["price"] * item["quantity"],
            }
            for barcode, item in cart.items()
        ]
    return {
        "items": items,
        "item_count": sum(item["quantity"] for item in items),
        "product_total": round(sum(item["line_total"] for item in items), 2),
    }


def publish_scan(code, found, message=None):
    global latest_scan_state
    with api_state_lock:
        latest_scan_state = {
            "id": str(uuid.uuid4()),
            "barcode": code,
            "found": found,
            "status": "found" if found else "not_found",
            "message": message,
            "scanned_at": datetime.now().astimezone().isoformat(),
        }


def update_session_snapshot(**fields):
    global active_session_state
    with api_state_lock:
        if active_session_state is not None:
            active_session_state.update(fields)


def finalize_session(session_start):
    """Freeze the completed session snapshot for the app and checkout response."""
    global active_session_state
    ended = datetime.now().astimezone()
    started = session_start.astimezone()
    duration = max(0, int((ended - started).total_seconds()))
    blocks = max(1, math.ceil(duration / (30 * 60)))
    cart_data = cart_snapshot()
    rental = blocks * SESSION_PRICE_RUPEES
    with api_state_lock:
        if active_session_state is not None:
            active_session_state.update({
                "status": "completed",
                "ended_at": ended.isoformat(),
                "duration_seconds": duration,
                "billing_periods": blocks,
                "usage_fee": rental,
                "product_total": cart_data["product_total"],
                "total_due": round(rental + cart_data["product_total"], 2),
                "cart": cart_data,
                "checked_out": checkout_requested.is_set(),
            })
    session_finished.set()


def start_api_server():
    """Serve the customer app API alongside the trolley loop."""
    try:
        from fastapi import FastAPI, HTTPException
        from fastapi.middleware.cors import CORSMiddleware
        import uvicorn

        app = FastAPI(title="Cartly Trolley API", version="1.0.0")
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost", "http://localhost:5173", "http://127.0.0.1:5173"],
            allow_origin_regex=r"http://(10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(1[6-9]|2[0-9]|3[01])\.\d{1,3}\.\d{1,3})(:\d+)?",
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["*"],
            expose_headers=["Date"],
        )

        @app.get("/health")
        def health():
            return {"status": "ok", "service": "cartly-api", "server_time": datetime.now().astimezone().isoformat()}

        @app.get("/api/trolley/status")
        def trolley_status():
            return {
                "connected": True,
                "status": "ok",
                "controller": motor_pwm_left is not None and motor_pwm_right is not None,
                "camera": camera_active,
                "scanner": barcode_scanner_active,
                "hardware_note": "API is running in the trolley process. Camera and barcode scanner status reflect their current session state.",
            }

        @app.get("/api/session/active")
        def active_session():
            with api_state_lock:
                current = dict(active_session_state) if active_session_state else None
            if current is None:
                return {"session": None, "server_time": datetime.now().astimezone().isoformat()}
            current["cart"] = cart_snapshot()
            current["product_total"] = current["cart"]["product_total"]
            return {"session": current, "server_time": datetime.now().astimezone().isoformat()}

        @app.get("/api/cart")
        def get_cart():
            return cart_snapshot()

        @app.get("/api/scans/latest")
        def latest_scan():
            with api_state_lock:
                return {"scan": dict(latest_scan_state) if latest_scan_state else None}

        @app.post("/api/checkout")
        def checkout():
            with api_state_lock:
                current = dict(active_session_state) if active_session_state else None
            if current is None:
                raise HTTPException(status_code=409, detail="There is no session to check out")
            if current.get("status") in ("completed", "ended", "checked_out"):
                if current.get("checked_out"):
                    return {"bill": current}
                raise HTTPException(status_code=409, detail="This session already ended at the trolley")

            checkout_requested.set()
            if not session_finished.wait(timeout=15):
                raise HTTPException(status_code=503, detail="The trolley did not finish checkout in time")
            with api_state_lock:
                completed = dict(active_session_state) if active_session_state else None
            if not completed or not completed.get("checked_out"):
                raise HTTPException(status_code=409, detail="The trolley session ended before checkout completed")
            return {"bill": completed}

        config = uvicorn.Config(app, host=API_HOST, port=API_PORT, log_level="warning", access_log=False)
        uvicorn.Server(config).run()
    except Exception as exc:
        print(f"[API] Could not start customer app API: {exc}")


# ============================================================
# MOTOR CONTROL
# ============================================================

def setup_gpio():

    global motor_pwm_left
    global motor_pwm_right

    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    for pin in (IN1, IN2, IN3, IN4, ENA, ENB):

        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, GPIO.LOW)

    motor_pwm_left = GPIO.PWM(ENA, 1000)
    motor_pwm_right = GPIO.PWM(ENB, 1000)

    motor_pwm_left.start(0)
    motor_pwm_right.start(0)

    print("[MOTOR] GPIO initialized.")
    print("[MOTOR] Movement enabled:", MOTOR_CONTROL_ENABLED)


def stop_motors():

    try:

        if motor_pwm_left is not None:
            motor_pwm_left.ChangeDutyCycle(0)

        if motor_pwm_right is not None:
            motor_pwm_right.ChangeDutyCycle(0)

        for pin in (IN1, IN2, IN3, IN4):
            GPIO.output(pin, GPIO.LOW)

    except Exception as exc:
        print("[MOTOR] Stop error:", exc)


def set_motor_pair(
    left_forward,
    right_forward,
    left_speed,
    right_speed
):

    if not MOTOR_CONTROL_ENABLED:
        stop_motors()
        return

    if REVERSE_LEFT_MOTOR:
        left_forward = not left_forward

    if REVERSE_RIGHT_MOTOR:
        right_forward = not right_forward

    GPIO.output(
        IN1,
        GPIO.HIGH if left_forward else GPIO.LOW
    )

    GPIO.output(
        IN2,
        GPIO.LOW if left_forward else GPIO.HIGH
    )

    GPIO.output(
        IN3,
        GPIO.HIGH if right_forward else GPIO.LOW
    )

    GPIO.output(
        IN4,
        GPIO.LOW if right_forward else GPIO.HIGH
    )

    motor_pwm_left.ChangeDutyCycle(
        max(0, min(100, left_speed))
    )

    motor_pwm_right.ChangeDutyCycle(
        max(0, min(100, right_speed))
    )


def move_forward():

    set_motor_pair(
        True,
        True,
        FORWARD_SPEED,
        FORWARD_SPEED
    )


def turn_left():

    set_motor_pair(
        False,
        True,
        TURN_SPEED,
        TURN_SPEED
    )


def turn_right():

    set_motor_pair(
        True,
        False,
        TURN_SPEED,
        TURN_SPEED
    )


# ============================================================
# LCD - TROLLEY BUDDY
# ============================================================

HAPPY = [
    0b00000,
    0b01010,
    0b01010,
    0b00000,
    0b10001,
    0b01110,
    0b00000,
    0b00000
]

FOCUSED = [
    0b00000,
    0b11111,
    0b01010,
    0b00000,
    0b01110,
    0b10001,
    0b00000,
    0b00000
]

SAD = [
    0b00000,
    0b01010,
    0b01010,
    0b00000,
    0b01110,
    0b10001,
    0b00000,
    0b00000
]

BLINK = [
    0b00000,
    0b00000,
    0b11111,
    0b00000,
    0b10001,
    0b01110,
    0b00000,
    0b00000
]


def setup_lcd():

    global lcd

    lcd = CharLCD(
        "PCF8574",
        address=LCD_ADDRESS,
        port=1,
        cols=16,
        rows=2,
        charmap="A00",
        auto_linebreaks=False
    )

    lcd.create_char(0, HAPPY)
    lcd.create_char(1, FOCUSED)
    lcd.create_char(2, SAD)
    lcd.create_char(3, BLINK)

    buddy(0, "Hey! Scan me :)")


def buddy(face, message):

    if lcd is None:
        return

    try:

        lcd.clear()

        lcd.cursor_pos = (0, 6)

        lcd.write_string(
            chr(face) + " " + chr(face)
        )

        lcd.cursor_pos = (1, 0)

        lcd.write_string(
            str(message)[:16].ljust(16)
        )

    except Exception as exc:

        print("[LCD]", exc)


def lcd_session_time(seconds):

    if lcd is None:
        return

    minutes = max(0, seconds // 60)
    secs = max(0, seconds % 60)

    try:

        lcd.cursor_pos = (1, 0)

        lcd.write_string(
            f"Time {minutes:02d}:{secs:02d}".ljust(16)
        )

    except Exception:
        pass


# ============================================================
# RFID
# ============================================================

def setup_rfid():

    global reader

    reader = SimpleMFRC522()


def wait_for_authorized_card():

    global authorized_card_id

    buddy(0, "Scan your RFID")

    print("[RFID] Waiting for card...")

    while True:

        try:

            card_id, _ = reader.read()

            print("[RFID] Card:", card_id)

            if card_id in AUTHORIZED_CARDS:

                authorized_card_id = str(card_id)

                print("[RFID] Authorized.")

                buddy(0, "Welcome!")

                return True

            print("[RFID] Unauthorized card.")

            buddy(2, "Card not valid")

            time.sleep(1.5)

            buddy(0, "Scan your RFID")

        except KeyboardInterrupt:
            raise

        except Exception as exc:

            print("[RFID] Read error:", exc)

            stop_motors()

            time.sleep(1)


# ============================================================
# BARCODE SCANNER
# ============================================================

def key_to_character(code):

    mapping = {

        ecodes.KEY_0: "0",
        ecodes.KEY_1: "1",
        ecodes.KEY_2: "2",
        ecodes.KEY_3: "3",
        ecodes.KEY_4: "4",
        ecodes.KEY_5: "5",
        ecodes.KEY_6: "6",
        ecodes.KEY_7: "7",
        ecodes.KEY_8: "8",
        ecodes.KEY_9: "9",

        ecodes.KEY_KP0: "0",
        ecodes.KEY_KP1: "1",
        ecodes.KEY_KP2: "2",
        ecodes.KEY_KP3: "3",
        ecodes.KEY_KP4: "4",
        ecodes.KEY_KP5: "5",
        ecodes.KEY_KP6: "6",
        ecodes.KEY_KP7: "7",
        ecodes.KEY_KP8: "8",
        ecodes.KEY_KP9: "9"
    }

    return mapping.get(code)


def barcode_reader_worker():

    global barcode_scanner_active

    devices = glob.glob(BARCODE_DEVICE_GLOB)

    if not devices:

        barcode_scanner_active = False

        print("[BARCODE] Scanner not found.")

        return

    device_path = devices[0]

    print("[BARCODE] Reading from:", device_path)

    try:

        device = InputDevice(device_path)
        barcode_scanner_active = True
        buffer = ""
        last_digit_at = None

        def submit_buffer():
            nonlocal buffer, last_digit_at
            code = buffer.strip()
            if code:
                barcode_queue.put(code)
                print("[BARCODE] Scanned:", code)
            buffer = ""
            last_digit_at = None

        while not barcode_stop.is_set():
            readable, _, _ = select.select([device.fd], [], [], 0.15)

            # Some HID scanners omit a suffix key. A short quiet period closes
            # the digit string so it still reaches the trolley's scan queue.
            if not readable:
                if buffer and last_digit_at is not None and time.monotonic() - last_digit_at >= 0.15:
                    submit_buffer()
                continue

            for event in device.read():
                if event.type != ecodes.EV_KEY or event.value != 1:
                    continue

                if event.code in (ecodes.KEY_ENTER, ecodes.KEY_KPENTER, ecodes.KEY_TAB):
                    submit_buffer()
                    continue

                now = time.monotonic()
                if buffer and last_digit_at is not None and now - last_digit_at >= 0.15:
                    submit_buffer()

                char = key_to_character(event.code)
                if char is not None:
                    buffer += char
                    last_digit_at = now

        if buffer:
            submit_buffer()
        device.close()

    except PermissionError:

        barcode_scanner_active = False

        print(
            "[BARCODE] Permission denied. "
            "Check input group permissions."
        )

    except OSError as exc:

        barcode_scanner_active = False

        if not barcode_stop.is_set():
            print("[BARCODE] Error:", exc)


def start_barcode_reader():

    global barcode_thread

    barcode_stop.clear()

    barcode_thread = threading.Thread(
        target=barcode_reader_worker,
        daemon=True
    )

    barcode_thread.start()


def stop_barcode_reader():

    global barcode_scanner_active
    barcode_stop.set()
    barcode_scanner_active = False


def process_barcode(code):

    product = PRODUCTS.get(code)

    if product is None:

        publish_scan(code, False, "Barcode was not found in the trolley product catalogue")

        print("[CART] Unknown barcode:", code)

        buddy(2, "Unknown product")

        time.sleep(0.8)

        buddy(0, "Following you")

        return

    removed = False
    with cart_lock:

        if code in cart:
            del cart[code]
            removed = True
        else:
            cart[code] = {
                "name": product["name"],
                "price": float(product["price"]),
                "quantity": 1
            }

    if removed:
        publish_scan(code, True, f"Removed {product['name']} from the cart")
        print(f"[CART] Removed {product['name']} from cart.")
        buddy(2, "Item removed")
    else:
        publish_scan(code, True, f"Added {product['name']}")
        print(f"[CART] Added {product['name']} Rs.{product['price']:.2f}")
        buddy(0, f"{product['name'][:8]} Rs{product['price']:.0f}")


def cart_total():

    with cart_lock:

        return sum(
            item["price"] * item["quantity"]
            for item in cart.values()
        )


def print_cart():

    print("\n========== SHOPPING CART ==========")

    with cart_lock:

        if not cart:

            print("Cart is empty.")

        else:

            for item in cart.values():

                line_total = (
                    item["price"] * item["quantity"]
                )

                print(
                    f"{item['name']} x "
                    f"{item['quantity']} = "
                    f"Rs.{line_total:.2f}"
                )

    print(f"TOTAL: Rs.{cart_total():.2f}")

    print("===================================\n")


# ============================================================
# YOLOV8 ONNX MODEL
# ============================================================

def load_model():

    global onnx_session
    global input_name
    global INPUT_SIZE
    global ppo_session
    global ppo_input_name

    print("[AI] Loading YOLOv8n ONNX...")

    onnx_session = ort.InferenceSession(
        MODEL_PATH,
        providers=["CPUExecutionProvider"]
    )

    input_name = onnx_session.get_inputs()[0].name

    detector_shape = onnx_session.get_inputs()[0].shape
    if isinstance(detector_shape[2], int) and isinstance(detector_shape[3], int):
        if detector_shape[2] != detector_shape[3]:
            raise RuntimeError("Detector ONNX model must use a square input")
        INPUT_SIZE = int(detector_shape[2])

    print("[AI] Loading PPO movement policy...")
    ppo_options = ort.SessionOptions()
    ppo_options.intra_op_num_threads = 2
    ppo_options.inter_op_num_threads = 1
    ppo_session = ort.InferenceSession(
        PPO_MODEL_PATH,
        sess_options=ppo_options,
        providers=["CPUExecutionProvider"]
    )
    ppo_input_name = ppo_session.get_inputs()[0].name

    print("[AI] YOLOv8n ONNX loaded.")
    print("[AI] PPO movement policy loaded.")


def preprocess(frame):

    height, width = frame.shape[:2]

    scale = min(
        INPUT_SIZE / width,
        INPUT_SIZE / height
    )

    new_width = int(round(width * scale))
    new_height = int(round(height * scale))

    resized = cv2.resize(
        frame,
        (new_width, new_height)
    )

    canvas = np.full(
        (INPUT_SIZE, INPUT_SIZE, 3),
        114,
        dtype=np.uint8
    )

    pad_x = (INPUT_SIZE - new_width) // 2
    pad_y = (INPUT_SIZE - new_height) // 2

    canvas[
        pad_y:pad_y + new_height,
        pad_x:pad_x + new_width
    ] = resized

    image = cv2.cvtColor(
        canvas,
        cv2.COLOR_BGR2RGB
    )

    image = image.astype(np.float32) / 255.0

    image = np.transpose(
        image,
        (2, 0, 1)
    )[None, ...]

    return image, scale, pad_x, pad_y


def detect_people(frame):

    global current_obstacle_distances
    height, width = frame.shape[:2]

    image, scale, pad_x, pad_y = preprocess(frame)

    output = onnx_session.run(
        None,
        {input_name: image}
    )[0]

    predictions = np.squeeze(output)

    if predictions.ndim != 2:
        current_obstacle_distances = [None, None, None]
        return []

    if predictions.shape[0] == 84 and predictions.shape[1] != 84:
        predictions = predictions.T
    if predictions.shape[1] != 84:
        current_obstacle_distances = [None, None, None]
        return []

    detections = []

    for row in predictions:

        class_scores = row[4:84]
        class_id = int(np.argmax(class_scores))
        score = float(class_scores[class_id])

        if score < CONFIDENCE_THRESHOLD:
            continue

        if class_id != 0 and class_id not in HAZARD_CLASS_HEIGHTS:
            continue

        cx, cy, bw, bh = row[:4]

        x1 = int(
            (cx - bw / 2 - pad_x) / scale
        )

        y1 = int(
            (cy - bh / 2 - pad_y) / scale
        )

        x2 = int(
            (cx + bw / 2 - pad_x) / scale
        )

        y2 = int(
            (cy + bh / 2 - pad_y) / scale
        )

        x1 = max(0, min(width - 1, x1))
        y1 = max(0, min(height - 1, y1))

        x2 = max(0, min(width - 1, x2))
        y2 = max(0, min(height - 1, y2))

        if x2 <= x1 or y2 <= y1:
            continue

        detections.append({
            "class_id": class_id,
            "score": score,
            "bbox": (x1, y1, x2, y2),
        })

    people = []
    current_obstacle_distances = [None, None, None]
    for class_id in {item["class_id"] for item in detections}:
        class_detections = [item for item in detections if item["class_id"] == class_id]
        boxes = [[item["bbox"][0], item["bbox"][1],
                  item["bbox"][2] - item["bbox"][0], item["bbox"][3] - item["bbox"][1]]
                 for item in class_detections]
        scores = [item["score"] for item in class_detections]
        indices = cv2.dnn.NMSBoxes(boxes, scores, CONFIDENCE_THRESHOLD, NMS_THRESHOLD)

        for idx in np.asarray(indices).reshape(-1):
            x1, y1, x2, y2 = class_detections[int(idx)]["bbox"]
            box_h = max(1.0, y2 - y1)
            box_cx = (x1 + x2) / 2.0

            if class_id == 0:
                people.append((x1, y1, x2, y2))
            else:
                estimated_range = CAMERA_FOCAL_Y_PX * HAZARD_CLASS_HEIGHTS[class_id] / box_h
                sector = 0 if abs(box_cx - width / 2) < width * 0.18 else (1 if box_cx < width / 2 else 2)
                current = current_obstacle_distances[sector]
                if current is None or estimated_range < current:
                    current_obstacle_distances[sector] = estimated_range

    return people


# ============================================================
# PERSON TRACKING
# ============================================================

def iou(a, b):

    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b

    x1 = max(ax1, bx1)
    y1 = max(ay1, by1)

    x2 = min(ax2, bx2)
    y2 = min(ay2, by2)

    intersection = (
        max(0, x2 - x1)
        * max(0, y2 - y1)
    )

    area_a = (
        max(0, ax2 - ax1)
        * max(0, ay2 - ay1)
    )

    area_b = (
        max(0, bx2 - bx1)
        * max(0, by2 - by1)
    )

    union = area_a + area_b - intersection

    if union <= 0:
        return 0.0

    return intersection / union


def select_initial_person(people, frame_width):

    if not people:
        return None

    frame_center = frame_width / 2

    return max(
        people,
        key=lambda box: (
            (box[2] - box[0])
            * (box[3] - box[1])
            - 2 * abs(
                ((box[0] + box[2]) / 2)
                - frame_center
            )
        )
    )


def match_locked_person(people, previous_box):

    if not people:
        return None

    candidate = max(
        people,
        key=lambda box: iou(box, previous_box)
    )

    if iou(candidate, previous_box) >= 0.20:
        return candidate

    return None


def control_following(box, frame_width, frame_height):

    x1, y1, x2, y2 = box

    center_x = (x1 + x2) / 2

    error = (
        center_x - frame_width / 2
    ) / (frame_width / 2)

    height_ratio = (
        y2 - y1
    ) / frame_height

    if height_ratio >= STOP_MIN_HEIGHT:

        stop_motors()

        return "STOP - TOO CLOSE"

    if error < -CENTER_DEAD_ZONE:

        turn_left()

        return "TURN LEFT"

    if error > CENTER_DEAD_ZONE:

        turn_right()

        return "TURN RIGHT"

    if height_ratio < FOLLOW_MIN_HEIGHT:

        move_forward()

        return "FOLLOWING"

    stop_motors()

    return "HOLD POSITION"


def control_following_ppo(box, frame_width, frame_height):
    """Use the trained PPO actor, then apply independent motion safety limits."""
    global ppo_previous_action
    global previous_linear_velocity
    global previous_angular_velocity

    if ppo_session is None:
        stop_motors()
        return "STOP - PPO unavailable"

    x1, y1, x2, y2 = box
    box_height = max(1.0, float(y2 - y1))
    center_x = (float(x1) + float(x2)) / 2.0
    distance = CAMERA_FOCAL_Y_PX * 1.70 / box_height
    focal_x = frame_width / (2.0 * math.tan(math.radians(CAMERA_HORIZONTAL_FOV_DEG) / 2.0))
    angle = math.atan((center_x - frame_width / 2.0) / focal_x)
    lateral = distance * math.sin(angle)

    front, left_range, right_range = current_obstacle_distances
    obs = np.asarray([
        np.clip(distance / 8.0, 0.0, 1.0),
        np.clip(lateral / 3.0, -1.0, 1.0),
        np.clip(angle / math.pi, -1.0, 1.0),
        np.clip((front if front is not None else VISION_UNKNOWN_RANGE_M) / 8.0, 0.0, 1.0),
        np.clip((left_range if left_range is not None else VISION_UNKNOWN_RANGE_M) / 8.0, 0.0, 1.0),
        np.clip((right_range if right_range is not None else VISION_UNKNOWN_RANGE_M) / 8.0, 0.0, 1.0),
        np.clip(previous_linear_velocity / 1.0, 0.0, 1.0),
        np.clip(previous_angular_velocity / 1.5, -1.0, 1.0),
        ppo_previous_action[0],
        ppo_previous_action[1],
    ], dtype=np.float32).reshape(1, 10)

    try:
        action = np.asarray(
            ppo_session.run(None, {ppo_input_name: obs})[0],
            dtype=np.float32
        ).reshape(-1)[:2]
        if action.size != 2 or not np.isfinite(action).all():
            raise ValueError("PPO produced invalid action")
    except Exception as exc:
        stop_motors()
        previous_linear_velocity = 0.0
        previous_angular_velocity = 0.0
        print("[PPO] Inference failed; motors stopped:", exc)
        return "STOP - PPO error"

    ppo_previous_action = np.clip(action, -1.0, 1.0).astype(np.float32)
    linear = (float(ppo_previous_action[0]) + 1.0) * 0.5
    angular = float(ppo_previous_action[1]) * 1.5
    linear = min(linear, MAX_LINEAR_SPEED_MPS)
    angular = float(np.clip(angular, -MAX_TURN_RATE_RADPS, MAX_TURN_RATE_RADPS))
    safety_reason = "PPO"

    if distance < MIN_FOLLOW_DISTANCE_M:
        linear = 0.0
        angular = 0.0
        safety_reason = "TOO CLOSE"
    elif front is None:
        linear = min(linear, UNKNOWN_RANGE_SPEED_MPS)
        angular = float(np.clip(angular, -UNKNOWN_RANGE_TURN_RADPS, UNKNOWN_RANGE_TURN_RADPS))
        safety_reason = "VISION ONLY - LIMITED"
    elif front < OBSTACLE_STOP_DISTANCE_M:
        linear = 0.0
        if left_range is not None and right_range is not None and max(left_range, right_range) > 0.8:
            angular = MAX_TURN_RATE_RADPS if left_range > right_range else -MAX_TURN_RATE_RADPS
        else:
            angular = 0.0
        safety_reason = "OBSTACLE STOP"
    elif front < OBSTACLE_SLOW_DISTANCE_M:
        linear = min(linear, UNKNOWN_RANGE_SPEED_MPS)
        safety_reason = "OBSTACLE SLOW"

    if left_range is None or right_range is None:
        angular = float(np.clip(angular, -UNKNOWN_RANGE_TURN_RADPS, UNKNOWN_RANGE_TURN_RADPS))
        if safety_reason == "PPO":
            safety_reason = "VISION ONLY - LIMITED"

    linear = float(np.clip(linear, 0.0, MAX_LINEAR_SPEED_MPS))
    angular = float(np.clip(angular, -MAX_TURN_RATE_RADPS, MAX_TURN_RATE_RADPS))

    left_mps = linear - angular * WHEEL_TRACK_M / 2.0
    right_mps = linear + angular * WHEEL_TRACK_M / 2.0
    left_norm = float(np.clip(left_mps / MAX_WHEEL_SPEED_MPS, -1.0, 1.0))
    right_norm = float(np.clip(right_mps / MAX_WHEEL_SPEED_MPS, -1.0, 1.0))
    set_motor_pair(
        left_norm >= 0.0,
        right_norm >= 0.0,
        abs(left_norm) * 100.0,
        abs(right_norm) * 100.0,
    )

    previous_linear_velocity = linear
    previous_angular_velocity = angular
    return f"PPO {safety_reason} v={linear:.2f} w={angular:.2f} d={distance:.2f}m"


# ============================================================
# SHOPPING SESSION
# ============================================================

def run_shopping_session():

    global active_session_state
    global camera_active
    global ppo_previous_action
    global previous_linear_velocity
    global previous_angular_velocity

    ppo_previous_action = np.zeros(2, dtype=np.float32)
    previous_linear_velocity = 0.0
    previous_angular_velocity = 0.0

    session_start = datetime.now()
    session_started_aware = session_start.astimezone()

    checkout_requested.clear()
    session_finished.clear()
    with api_state_lock:
        active_session_state = {
            "session_id": str(uuid.uuid4()),
            "card_id": authorized_card_id,
            "started_at": session_started_aware.isoformat(),
            "status": "active",
            "can_checkout": True,
            "checked_out": False,
        }

    session_end = (
        session_start
        + timedelta(minutes=SESSION_MINUTES)
    )

    print(
        "\n[SESSION] Started:",
        session_start.strftime("%H:%M:%S")
    )

    print(
        f"[SESSION] Charge: Rs.{SESSION_PRICE_RUPEES} "
        f"for {SESSION_MINUTES} minutes"
    )

    print(
        "[SESSION] RFID activation is not payment processing."
    )

    with cart_lock:
        cart.clear()

    camera = cv2.VideoCapture(CAMERA_INDEX)

    if not camera.isOpened():

        stop_motors()

        buddy(2, "Camera error!")

        print("[CAMERA] Could not open camera.")

        finalize_session(session_started_aware)

        return

    camera_active = True

    camera.set(
        cv2.CAP_PROP_FRAME_WIDTH,
        640
    )

    camera.set(
        cv2.CAP_PROP_FRAME_HEIGHT,
        480
    )

    print("[CAMERA] Camera started.")

    start_barcode_reader()

    locked = False

    target_box = None
    candidate_box = None
    candidate_since = None

    last_seen = time.monotonic()
    target_lost_reported = False
    last_lcd_time = 0.0

    last_barcode = None
    last_barcode_time = 0.0

    # Require card removal before accepting second scan.
    rfid_armed = False
    rfid_last_seen = time.monotonic()

    buddy(3, "Looking for you")

    print("[CAMERA] Stand in front of camera for 5 seconds.")

    print("[SYSTEM] Running in headless mode.")
    print("[SYSTEM] No OpenCV display window will open.")
    print("[SYSTEM] Use Ctrl+C in the terminal to stop.")

    try:

        while datetime.now() < session_end and not checkout_requested.is_set():

            remaining = int(
                (session_end - datetime.now()).total_seconds()
            )

            if remaining <= 0:
                break

            # --------------------------------------------
            # SECOND RFID SCAN
            # --------------------------------------------

            try:

                scanned_id = reader.read_id_no_block()

            except Exception as exc:

                scanned_id = None

                print("[RFID] Scan warning:", exc)

            now_rfid = time.monotonic()

            if scanned_id is None:

                if now_rfid - rfid_last_seen >= 1.5:
                    rfid_armed = True

            else:

                rfid_last_seen = now_rfid

                if (
                    rfid_armed
                    and scanned_id in AUTHORIZED_CARDS
                ):

                    print("[RFID] Same card scanned again.")

                    print("[RFID] Session stop requested.")

                    buddy(0, "Session stopping")

                    stop_motors()

                    break

            # --------------------------------------------
            # PROCESS BARCODE SCANS
            # --------------------------------------------

            while True:

                try:

                    code = barcode_queue.get_nowait()

                except queue.Empty:

                    break

                now = time.monotonic()

                if (
                    code != last_barcode
                    or now - last_barcode_time > BARCODE_DUPLICATE_GUARD_SECONDS
                ):

                    process_barcode(code)

                    last_barcode = code
                    last_barcode_time = now

            # --------------------------------------------
            # CAMERA FRAME
            # --------------------------------------------

            ret, frame = camera.read()

            if not ret:

                stop_motors()

                buddy(2, "Camera lost!")

                print("[CAMERA] Frame read failed.")

                break

            frame_h, frame_w = frame.shape[:2]

            people = detect_people(frame)

            # --------------------------------------------
            # TARGET LOCKING
            # --------------------------------------------

            if not locked:

                current = select_initial_person(
                    people,
                    frame_w
                )

                if current is None:

                    candidate_box = None
                    candidate_since = None

                    stop_motors()

                    buddy(3, "Looking for you")

                else:

                    if candidate_box is None:

                        candidate_box = current

                        candidate_since = time.monotonic()

                    elif iou(candidate_box, current) >= 0.30:

                        candidate_box = current

                    else:

                        candidate_box = current

                        candidate_since = time.monotonic()

                    elapsed = (
                        time.monotonic()
                        - candidate_since
                    )

                    stop_motors()

                    buddy(
                        1,
                        f"Locking {int(elapsed)} sec"
                    )

                    if elapsed >= LOCK_SECONDS:

                        target_box = candidate_box

                        locked = True

                        last_seen = time.monotonic()

                        print("[TRACKING] Target locked!")

                        buddy(0, "Got you!")

            # --------------------------------------------
            # FOLLOW LOCKED PERSON
            # --------------------------------------------

            else:

                matched = match_locked_person(
                    people,
                    target_box
                )

                if matched is None:

                    stop_motors()

                    if (
                        time.monotonic() - last_seen
                        > TARGET_LOST_SECONDS
                    ):
                        buddy(2, "Where are you?")
                        if not target_lost_reported:
                            print("[TRACKING] Locked target lost. Motors stopped; target will not be replaced.")
                            target_lost_reported = True

                else:

                    target_box = matched

                    last_seen = time.monotonic()
                    target_lost_reported = False

                    status = control_following_ppo(
                        target_box,
                        frame_w,
                        frame_h
                    )

                    if (
                        time.monotonic() - last_lcd_time
                        >= 1.0
                    ):

                        buddy(1, "Following you!")

                        lcd_session_time(remaining)

                        last_lcd_time = time.monotonic()

                    print(
                        f"\r[TRACKING] {status} | "
                        f"Session {remaining // 60:02d}:"
                        f"{remaining % 60:02d}",
                        end="",
                        flush=True
                    )

            time.sleep(0.001)

    except KeyboardInterrupt:

        print("\n[SESSION] Interrupted by user.")

    finally:

        stop_motors()

        stop_barcode_reader()

        camera.release()
        camera_active = False

        print("\n[CAMERA] Camera stopped.")

    if datetime.now() >= session_end:

        buddy(2, "Session expired")

        print("[SESSION] Expired.")

    else:

        buddy(0, "Session ended")

        print("[SESSION] Ending.")

    print_cart()

    print(
        "[SESSION] Cart total: Rs.",
        f"{cart_total():.2f}"
    )

    print("[SESSION] No payment has been collected.")

    finalize_session(session_started_aware)

    time.sleep(2)


# ============================================================
# MAIN
# ============================================================

def main():

    global api_server_thread

    try:

        load_product_catalogue()

        setup_gpio()

        setup_lcd()

        setup_rfid()

        load_model()

        stop_motors()

        api_server_thread = threading.Thread(
            target=start_api_server,
            name="cartly-api",
            daemon=True,
        )
        api_server_thread.start()

        print("\n======================================")

        print("       SMART TROLLEY SYSTEM")

        print("======================================")

        print(
            "Motor control enabled:",
            MOTOR_CONTROL_ENABLED
        )

        print(f"PPO linear speed limit: {MAX_LINEAR_SPEED_MPS:.2f} m/s")
        print(f"Unknown-range crawl limit: {UNKNOWN_RANGE_SPEED_MPS:.2f} m/s")
        print("Obstacle ranges: camera detections only")

        print("AI model: YOLOv8n ONNX")
        print("Movement policy: PPO ONNX")

        print("Barcode scanner: USB HID")

        print("Session: Rs.20 / 30 minutes")

        print("Display mode: Headless")

        print(f"Customer app API: http://0.0.0.0:{API_PORT}")

        print("======================================\n")

        while True:

            stop_motors()

            wait_for_authorized_card()

            run_shopping_session()

            stop_motors()

            buddy(0, "Scan your RFID")

            print("[SYSTEM] Ready for next customer.")

    except KeyboardInterrupt:

        print("\n[MAIN] Shutdown requested.")

    finally:

        stop_motors()

        stop_barcode_reader()

        try:

            if motor_pwm_left is not None:
                motor_pwm_left.stop()

            if motor_pwm_right is not None:
                motor_pwm_right.stop()

            GPIO.cleanup()

        except Exception:
            pass

        try:

            if lcd is not None:

                lcd.clear()

                lcd.write_string("System stopped")

                lcd.close(clear=True)

        except Exception:
            pass

        print("[MAIN] Safe shutdown complete.")


if __name__ == "__main__":

    main()
