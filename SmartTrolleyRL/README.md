# Smart Trolley RL

This upgrades the existing Webots R2025a project in place. The fast PPO training plant is a seeded Gymnasium differential-drive model; the Webots world is the visual runtime and can load the saved PPO policy. Both use the same normalized 10-value observation and 2-value continuous action contract. The Webots demo uses Supervisor target coordinates for its virtual human target; the Raspberry Pi path uses the USB webcam instead.

The Webots trolley moves kinematically for stability on older integrated graphics. Its virtual range sensors enforce obstacle overrides, but the model does not simulate full tire, drivetrain, or contact dynamics. The Gym environment provides randomized obstacles, wall/object collision termination, virtual ray-cast sensors, seeded trajectory randomization, and easy/medium/hard scenarios. Do not treat this simulation as hardware safety validation.

## Install on Windows

Use 64-bit Python 3.11 or 3.12 for broad wheel support. From PowerShell:

```powershell
cd "C:\Users\kishore\Desktop\new app\SmartTrolleyRL"
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

The current machine's Python can also run the project once those requirements are installed. For PPO inference inside Webots, set **Tools > Preferences > Python command** to the same Python environment that has Stable-Baselines3 and PyTorch. Without those packages, the Webots controller uses its feedback baseline.

## Run the Webots simulation

Open `worlds/smart_trolley_rl.wbt` in Webots R2025a or run:

```powershell
& 'C:\Program Files\Webots\msys64\mingw64\bin\webots.exe' worlds\smart_trolley_rl.wbt
```

The designated person is `DEF TARGET_HUMAN`; the other two moving pedestrians are `DISTRACTOR_A` and `DISTRACTOR_B`. The trolley controller reads only `TARGET_HUMAN`, so distractors are never selected as the follow target. The world includes two long shelves, two aisle displays, walls, and correctly oriented virtual front/left/right range sensors. A clear-side steering override slows or redirects the trolley when a display is close. With no trained model it uses a feedback baseline. After training, close/reload the world; if `models/ppo_trolley.zip` is present, `trolley_controller` attempts to load it and applies the separate distance/range safety override. Target coordinates in Webots are Supervisor ground truth for this initial learning stage.

## Train PPO

From the project root:

```powershell
python -m rl.train
python -m rl.train --timesteps 100000 --seed 42 --difficulty easy --run-name experiment_easy
```

Default training uses 500,000 steps, CPU, a small `[64, 64]` MLP, and medium randomized scenarios. Use `--difficulty easy|medium|hard`, `--seed`, `--timesteps`, or `--checkpoint-freq` to adjust it. The final model is saved to `models/ppo_trolley.zip`; periodic checkpoints go in `models/checkpoints/`. Logs are saved under `logs/<run-name>/`, including `monitor.csv` for episode reward and `episode_metrics.csv` for mean following-distance error and collision count. TensorBoard scalars are written under `logs/`:

```powershell
tensorboard --logdir logs
```

Look for episode reward trending upward, distance error trending down, and collision count falling. PPO training is stochastic; compare multiple seeds and do not infer hardware readiness from reward alone.

## Evaluate and view the learned policy

```powershell
python -m rl.evaluate --model models/ppo_trolley --episodes 10 --difficulty medium
python -m rl.evaluate --model models/ppo_trolley --episodes 3 --render
python -m rl.evaluate --model models/ppo_trolley --episodes 5 --webots
```

Evaluation reports mean reward, mean following-distance error, and collision counts. `--render` prints Gym state per step. `--webots` opens the rendered world after metrics; for an existing Webots window, restart/reload the world after training to load the new model.

## Observation, actions, and rewards

The 10 normalized observation values are: `[human_distance/8, human_lateral/3, relative_angle/pi, front_range/8, left_range/8, right_range/8, current_linear_velocity/1, current_angular_velocity/1.5, previous_linear_action, previous_angular_action]`. Values are clipped to their documented normalized bounds. Actions are continuous normalized values `[-1,1]`; the linear component maps to `[0,1] m/s`, and angular maps to `[-1.5,1.5] rad/s`. The differential-drive controller converts those into left/right wheel speeds.

Reward terms are configurable in `rl/config.py`: desired-distance tracking, alignment, progress toward the distance setpoint, smooth action changes, turning/oscillation, obstacle clearance, close following, lost target, collision, and unnecessary stopping.

## Raspberry Pi 4 (2 GB) deployment

Train on this Windows PC or another training machine. The Pi runs camera and PPO inference only. The current hardware path uses no Arduino and assumes no ultrasonic or IR hardware. YOLO + ByteTrack assigns person IDs. `--target-selection manual` lets you click the intended person at startup; `nearest` locks the largest/nearest person box once. The selected ID is never silently changed: if it disappears, the safety layer stops instead of following another person. It has:

- `pi_controller/camera_perception.py`: USB webcam + YOLOv8n ONNX detections using ONNX Runtime, plus short-term IoU person-track IDs. No PyTorch runtime is needed on the Pi. Apparent object height estimates approximate distance using camera calibration.
- `pi_controller/inference.py`: ONNX Runtime CPU policy inference.
- `pi_controller/safety_controller.py`: independent speed/turn limits, stop on target loss, stop on inference failure, close-human stop, obstacle overrides, and E-stop handling.
- `pi_controller/gpio_motor_driver.py`: Raspberry Pi GPIO PWM to two L298N bridges, one channel per trolley side. Two left motors and two right motors may be wired in parallel only if each combined stall current is within the driver board's limits.
- `pi_controller/run_hardware.py`: end-to-end loop. Start with `--dry-run` so it cannot energize motor pins.

Export the PPO policy on the training computer (install `onnx` from `requirements.txt`):

```powershell
python -m rl.export_model --model models/ppo_trolley --output models/ppo_trolley.onnx
```

Export a small camera detector to ONNX on the training computer (the Pi only runs it with ONNX Runtime), then copy both ONNX models and `pi_controller/` to the Pi:

```powershell
yolo export model=yolov8n.pt format=onnx imgsz=320
```

On 64-bit Raspberry Pi OS, create a virtual environment and install `pi_controller/requirements-pi.txt`. This Pi requirements file intentionally omits PyTorch and Ultralytics to avoid their large install footprint. Copy `camera_calibration.example.json` to `camera_calibration.json`, then measure the actual webcam focal length and horizontal field of view. Use `nearest` selection over SSH; `manual` clicking requires a local graphical display. Run dry first:

```bash
python pi_controller/run_hardware.py --dry-run \
  --policy models/ppo_trolley.onnx --detector models/yolov8n.onnx \
  --target-selection nearest
```

For the existing RFID/barcode/LCD app supplied by the user, `pi_controller/smart_trolley_ppo.py` is an integrated variant that preserves those features and routes following actions through PPO. It expects the original detector at `/home/kishore/smart-trolley/yolov8n.onnx` and the PPO actor at `/home/kishore/SmartTrolleyRL/models/ppo_trolley.onnx`. The camera-only unknown-range mode allows up to 0.16 m/s and limits turning while no recognized obstacle is visible. YOLO COCO can miss shelves and walls, so use this only in a clear, supervised test area at low speed. The script stops if the locked person is lost and does not switch to another person.

After reviewing detection and distance output with wheels lifted, remove `--dry-run` only when the driver wiring, current budget, E-stop, and low speed limits have been checked. L298N pins follow `smart_trolley_raspberry_pi_wiring_guide.pdf`: left channel IN1=BCM17, IN2=BCM27, ENA=BCM18; right channel IN3=BCM22, IN4=BCM23, ENB=BCM19. The normally-closed E-stop loop is assigned BCM GPIO24 (physical pin 18), connected to GND; pressing it or breaking its wire latches a software stop until the process restarts. Add a separate latching battery cutoff for motor power. GPIO values in code are BCM numbers, not header pin numbers.

### Camera-only limits and motor power

A single webcam does not directly measure depth. The apparent-size distance estimates can be wrong when a person/object turns, is partly hidden, has an unknown size, or appears against clutter. COCO YOLOv8n does not recognize every shelf or obstacle. The software therefore limits speed/turning and creeps slowly when range confidence is missing, but this cannot guarantee collision avoidance. Use low speed, a clear test area, supervision, and a physical power cutoff. For dependable real-world obstacle protection, add a depth-capable camera or another suitable safety sensor later; the current provided hardware list does not include one.

The Raspberry Pi GPIO is 3.3 V logic and is not 5 V tolerant. Do not connect motors directly to GPIO. The battery powers the motor driver; use a properly rated buck regulator for the Pi and join grounds as required by the driver circuit. Check the motor stall current and thermal limits before paralleling four motors: ST lists the L298 at up to 4 A total DC current, and breakout-board cooling/current limits can be lower. See the [Raspberry Pi GPIO documentation](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#gpio) and [ST L298 datasheet](https://www.st.com/resource/en/datasheet/l298.pdf).

RFID, LCD, and HC-05 are not required by this control loop; they can be integrated later for inventory, status, or telemetry.

## Files

```text
worlds/smart_trolley_rl.wbt
controllers/trolley_controller/trolley_controller.py
controllers/human_controller/human_controller.py  controllers/distractor_controller/distractor_controller.py
rl/config.py  rl/environment.py  rl/rewards.py  rl/train.py  rl/evaluate.py  rl/export_model.py
pi_controller/camera_perception.py  pi_controller/inference.py
pi_controller/safety_controller.py  pi_controller/gpio_motor_driver.py  pi_controller/run_hardware.py
models/  logs/
```
