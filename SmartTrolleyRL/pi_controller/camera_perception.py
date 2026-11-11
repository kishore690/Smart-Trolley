"""USB webcam detection using ONNX Runtime and a small IoU person tracker.

The detector is an Ultralytics YOLOv8 COCO ONNX export (standard 4+80 output).
No PyTorch/Ultralytics runtime is needed on the Raspberry Pi.
"""
import math
import cv2
import numpy as np


HAZARD_HEIGHT_M = {
    "chair": 0.9, "couch": 0.9, "potted plant": 0.8, "bed": 0.55,
    "dining table": 0.75, "toilet": 0.75, "microwave": 0.35,
    "oven": 0.9, "sink": 0.9, "refrigerator": 1.7,
}
COCO_NAMES = {
    0: "person", 56: "chair", 57: "couch", 58: "potted plant", 59: "bed",
    60: "dining table", 61: "toilet", 68: "microwave", 69: "oven",
    71: "sink", 72: "refrigerator",
}


def _iou(a, b):
    x1=max(a[0],b[0]); y1=max(a[1],b[1])
    x2=min(a[2],b[2]); y2=min(a[3],b[3])
    intersection=max(0.0,x2-x1)*max(0.0,y2-y1)
    area_a=max(0.0,a[2]-a[0])*max(0.0,a[3]-a[1])
    area_b=max(0.0,b[2]-b[0])*max(0.0,b[3]-b[1])
    return intersection/max(1e-6,area_a+area_b-intersection)


class SimpleIoUTracker:
    """Keep short-lived IDs using same-class box overlap; never re-lock lost IDs."""
    def __init__(self, max_missed=15, min_iou=0.08):
        self.max_missed=int(max_missed); self.min_iou=float(min_iou)
        self.next_id=1; self.tracks={}

    def update(self, detections):
        candidates=[]
        for track_id, track in self.tracks.items():
            for index, detection in enumerate(detections):
                if track["class_id"] == detection["class_id"]:
                    overlap=_iou(track["bbox"],detection["bbox"])
                    if overlap>=self.min_iou:
                        candidates.append((overlap,track_id,index))
        assigned_tracks=set(); assigned_detections=set()
        for overlap,track_id,index in sorted(candidates,reverse=True):
            if track_id in assigned_tracks or index in assigned_detections:
                continue
            detections[index]["track_id"]=track_id
            self.tracks[track_id]={"bbox":detections[index]["bbox"],
                                   "class_id":detections[index]["class_id"],"missed":0}
            assigned_tracks.add(track_id); assigned_detections.add(index)
        for track_id in list(self.tracks):
            if track_id not in assigned_tracks:
                self.tracks[track_id]["missed"]+=1
                if self.tracks[track_id]["missed"]>self.max_missed:
                    del self.tracks[track_id]
        for index,detection in enumerate(detections):
            if index not in assigned_detections:
                track_id=self.next_id; self.next_id+=1
                detection["track_id"]=track_id
                self.tracks[track_id]={"bbox":detection["bbox"],
                                       "class_id":detection["class_id"],"missed":0}
        return detections


class OnnxYoloDetector:
    """Run a standard YOLOv8 COCO ONNX model using CPUExecutionProvider."""
    def __init__(self, model_path, image_size=320, confidence=0.35, nms_iou=0.45):
        import onnxruntime as ort
        options=ort.SessionOptions()
        options.intra_op_num_threads=2
        options.inter_op_num_threads=1
        self.session=ort.InferenceSession(model_path,sess_options=options,
                                          providers=["CPUExecutionProvider"])
        self.input_name=self.session.get_inputs()[0].name
        shape=self.session.get_inputs()[0].shape
        self.input_h=int(shape[2]) if isinstance(shape[2],int) else int(image_size)
        self.input_w=int(shape[3]) if isinstance(shape[3],int) else int(image_size)
        self.confidence=float(confidence); self.nms_iou=float(nms_iou)

    def detect(self, frame):
        height,width=frame.shape[:2]
        scale=min(self.input_w/width,self.input_h/height)
        resized_w=max(1,int(round(width*scale))); resized_h=max(1,int(round(height*scale)))
        resized=cv2.resize(frame,(resized_w,resized_h),interpolation=cv2.INTER_LINEAR)
        pad_x=(self.input_w-resized_w)//2; pad_y=(self.input_h-resized_h)//2
        canvas=np.full((self.input_h,self.input_w,3),114,dtype=np.uint8)
        canvas[pad_y:pad_y+resized_h,pad_x:pad_x+resized_w]=resized
        tensor=canvas[:,:,::-1].transpose(2,0,1)[None].astype(np.float32)/255.0
        raw=self.session.run(None,{self.input_name:tensor})[0]
        prediction=np.asarray(raw)
        if prediction.ndim==3:
            prediction=prediction[0]
        if prediction.ndim!=2:
            raise RuntimeError(f"Unsupported YOLO ONNX output shape: {raw.shape}")

        # Standard YOLOv8 output is [1, 4+classes, candidates].
        if prediction.shape[0] in (84,85) and prediction.shape[1]>prediction.shape[0]:
            prediction=prediction.T
        detections=[]
        for row in prediction:
            if row.shape[0]==6:
                # Also accept NMS-export output: x1,y1,x2,y2,score,class.
                x1,y1,x2,y2,score,class_id=map(float,row)
                class_id=int(class_id)
            elif row.shape[0]>=84:
                class_scores=row[4:84]
                class_id=int(np.argmax(class_scores)); score=float(class_scores[class_id])
                if class_id not in COCO_NAMES:
                    continue
                cx,cy,bw,bh=map(float,row[:4])
                x1=cx-bw/2; y1=cy-bh/2; x2=cx+bw/2; y2=cy+bh/2
            else:
                raise RuntimeError(f"Expected YOLOv8 4+80 output, got {raw.shape}")
            if score<self.confidence or class_id not in COCO_NAMES:
                continue
            x1=max(0.0,min(float(width),(x1-pad_x)/scale))
            y1=max(0.0,min(float(height),(y1-pad_y)/scale))
            x2=max(0.0,min(float(width),(x2-pad_x)/scale))
            y2=max(0.0,min(float(height),(y2-pad_y)/scale))
            if x2<=x1 or y2<=y1:
                continue
            detections.append({"bbox":(x1,y1,x2,y2),"score":score,"class_id":class_id})

        # Class-wise NMS; avoid torchvision/PyTorch dependencies.
        kept=[]
        for class_id in {item["class_id"] for item in detections}:
            group=[item for item in detections if item["class_id"]==class_id]
            boxes=[[d["bbox"][0],d["bbox"][1],d["bbox"][2]-d["bbox"][0],d["bbox"][3]-d["bbox"][1]] for d in group]
            indices=cv2.dnn.NMSBoxes(boxes,[d["score"] for d in group],self.confidence,self.nms_iou)
            for index in np.asarray(indices).reshape(-1):
                kept.append(group[int(index)])
        return kept


class PersonTargetLock:
    """Select one track ID and never silently switch to another person."""
    def __init__(self, mode="nearest"):
        if mode not in ("nearest", "manual"):
            raise ValueError("target selection mode must be 'nearest' or 'manual'")
        self.mode=mode; self.track_id=None

    def lock(self, track_id):
        if track_id is None:
            raise ValueError("cannot lock a person without a tracker ID")
        self.track_id=int(track_id)

    def choose(self, people):
        if self.track_id is None and self.mode=="nearest":
            identified=[person for person in people if person["track_id"] is not None]
            if identified:
                self.track_id=max(identified,key=lambda person:person["area"])["track_id"]
        if self.track_id is None:
            return None
        return next((person for person in people if person["track_id"]==self.track_id),None)


class CameraPerception:
    def __init__(self, model_path="yolov8n.onnx", camera_index=0,
                 focal_y_px=500.0, horizontal_fov_deg=69.0, image_size=320,
                 confidence=0.35, target_selection="nearest"):
        self.model=OnnxYoloDetector(model_path,image_size,confidence)
        self.camera=cv2.VideoCapture(camera_index)
        if not self.camera.isOpened():
            raise RuntimeError(f"USB camera {camera_index} could not be opened")
        self.focal_y=float(focal_y_px)
        self.horizontal_fov=math.radians(horizontal_fov_deg)
        self.target_lock=PersonTargetLock(target_selection)
        self.tracker=SimpleIoUTracker()
        self.last_people=[]; self._clicked_track_id=None

    @property
    def target_track_id(self):
        return self.target_lock.track_id

    def _mouse_select(self,event,x,y,flags,userdata):
        if event==cv2.EVENT_LBUTTONDOWN:
            for person in self.last_people:
                x1,y1,x2,y2=person["bbox"]
                if x1<=x<=x2 and y1<=y<=y2:
                    self._clicked_track_id=person["track_id"]
                    return

    def select_target_interactively(self):
        if self.target_track_id is not None:
            return self.target_track_id
        if self.target_lock.mode!="manual":
            raise RuntimeError("interactive selection requires target_selection='manual'")
        window="Select trolley follow target"
        try:
            cv2.namedWindow(window)
            cv2.setMouseCallback(window,self._mouse_select)
        except cv2.error as exc:
            raise RuntimeError("Manual selection needs a GUI-enabled OpenCV build and local display; use nearest mode over SSH") from exc
        try:
            while self.target_track_id is None:
                result=self.read()
                if result is None:
                    cv2.waitKey(1); continue
                frame=result["frame"].copy()
                for person in self.last_people:
                    x1,y1,x2,y2=map(int,person["bbox"]); track=person["track_id"]
                    cv2.rectangle(frame,(x1,y1),(x2,y2),(50,220,50),2)
                    cv2.putText(frame,f"ID {track}",(x1,max(20,y1-8)),cv2.FONT_HERSHEY_SIMPLEX,0.6,(50,220,50),2)
                cv2.putText(frame,"Click the person to follow | Q quits",(12,28),cv2.FONT_HERSHEY_SIMPLEX,0.65,(0,255,255),2)
                cv2.imshow(window,frame); key=cv2.waitKey(1)&0xFF
                if key==ord("q"):
                    raise RuntimeError("target selection cancelled")
                if self._clicked_track_id is not None:
                    self.target_lock.lock(self._clicked_track_id); self._clicked_track_id=None
            return self.target_track_id
        finally:
            cv2.destroyWindow(window)

    def read(self):
        ok,frame=self.camera.read()
        if not ok or frame is None:
            return None
        height,width=frame.shape[:2]
        fx=width/(2*math.tan(self.horizontal_fov/2))
        detections=self.tracker.update(self.model.detect(frame))
        people=[]; hazards=[None,None,None]; center=width/2
        for detection in detections:
            class_id=detection["class_id"]; label=COCO_NAMES[class_id]
            x1,y1,x2,y2=detection["bbox"]
            box_h=max(1.0,y2-y1); box_cx=(x1+x2)/2
            if label=="person":
                angle=math.atan((box_cx-center)/fx)
                people.append({"track_id":detection["track_id"],"bbox":(x1,y1,x2,y2),
                               "height":box_h,"area":(x2-x1)*box_h,
                               "distance_m":self.focal_y*1.70/box_h,"angle_rad":angle})
            elif label in HAZARD_HEIGHT_M:
                estimate=self.focal_y*HAZARD_HEIGHT_M[label]/box_h
                sector=0 if abs(box_cx-center)<width*0.18 else (1 if box_cx<center else 2)
                if hazards[sector] is None or estimate<hazards[sector]:
                    hazards[sector]=estimate
        self.last_people=people; target=self.target_lock.choose(people)
        if target is None:
            return {"frame":frame,"target_visible":False,"target_track_id":self.target_track_id,
                    "distance_m":None,"angle_rad":None,"lateral_m":None,
                    "obstacle_distances_m":hazards,"people_count":len(people)}
        distance=target["distance_m"]; angle=target["angle_rad"]
        return {"frame":frame,"target_visible":True,"target_track_id":self.target_track_id,
                "distance_m":distance,"angle_rad":angle,"lateral_m":distance*math.sin(angle),
                "obstacle_distances_m":hazards,"people_count":len(people)}

    def close(self):
        self.camera.release()
