"""Camera -> PPO -> independent safety controller -> Raspberry Pi GPIO/L298N."""
import argparse
import json
from pathlib import Path
import time
import numpy as np
from inference import Policy
from camera_perception import CameraPerception
from safety_controller import SafetyController, SafetyLimits


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--policy",default="models/ppo_trolley.onnx")
    parser.add_argument("--detector",default="yolov8n.onnx")
    parser.add_argument("--calibration",default="pi_controller/camera_calibration.json")
    parser.add_argument("--target-selection",choices=("nearest","manual"),default="nearest",
                        help="auto-lock nearest/largest person or click the intended person at startup")
    parser.add_argument("--dry-run",action="store_true",help="run camera/policy but never energize motor pins")
    args=parser.parse_args()
    policy=Policy(args.policy)
    calibration=Path(args.calibration)
    camera_cfg=json.loads(calibration.read_text(encoding="utf-8")) if calibration.exists() else {}
    perception=CameraPerception(args.detector,
                                focal_y_px=camera_cfg.get("focal_y_px",500.0),
                                horizontal_fov_deg=camera_cfg.get("horizontal_fov_deg",69.0),
                                image_size=camera_cfg.get("image_size",320),
                                target_selection=args.target_selection)
    if args.target_selection=="manual":
        chosen=perception.select_target_interactively()
        print(f"Locked follow target track ID {chosen}; other person IDs will be ignored")
    safety=SafetyController(SafetyLimits())
    if args.dry_run:
        motors=None
    else:
        from gpio_motor_driver import GPIOMotorDriver
        motors=GPIOMotorDriver()
    previous_action=np.zeros(2,dtype=np.float32)
    linear_velocity=0.0; angular_velocity=0.0
    try:
        while True:
            try:
                observation=perception.read()
                if observation is None:
                    raise RuntimeError("camera frame unavailable")
                detected=observation["target_visible"]
                distance=observation["distance_m"]
                angle=observation["angle_rad"]
                lateral=observation["lateral_m"]
                front,left,right=observation["obstacle_distances_m"]
                # Unknown monocular range is encoded as zero: conservative input.
                obs=np.asarray([
                    min(distance if distance is not None else 8.0,8.0)/8.0,
                    max(-3.0,min(3.0,lateral or 0.0))/3.0,
                    max(-1.0,min(1.0,(angle or 0.0)/np.pi)),
                    (front or 0.0)/8.0,(left or 0.0)/8.0,(right or 0.0)/8.0,
                    max(0.0,min(1.0,linear_velocity)),
                    max(-1.0,min(1.0,angular_velocity/1.5)),
                    previous_action[0],previous_action[1],
                ],dtype=np.float32)
                action=policy.act(obs)
                v,w,reason=safety.limit(action,target_visible=detected,target_distance_m=distance,
                                         obstacle_distances_m=(front,left,right),
                                         inference_ok=True,
                                         emergency_stop=motors.estop_pressed() if motors else False)
                linear_velocity=v; angular_velocity=w
                previous_action=np.asarray([2*v/1.0-1.0,w/1.5],dtype=np.float32)
                # Differential-drive inverse kinematics, then safe normalized PWM.
                track_width=0.52; max_wheel_speed=0.45
                vl=v-w*track_width/2; vr=v+w*track_width/2
                if motors:
                    motors.drive(vl/max_wheel_speed,vr/max_wheel_speed)
                print(f"target_id={observation['target_track_id']} "
                      f"target={distance if distance is not None else 'lost'}m "
                      f"people={observation['people_count']} v={v:.2f} w={w:.2f} safety={reason}")
            except Exception as exc:
                if motors: motors.stop()
                linear_velocity=0.0; angular_velocity=0.0
                print(f"FAIL-SAFE STOP: {exc}")
                time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        if motors: motors.close()
        perception.close()


if __name__=="__main__": main()
