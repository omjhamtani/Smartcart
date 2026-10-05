import time
from pathlib import Path
from typing import Callable, Optional

import cv2
import torch
from ultralytics import YOLO

from config import CLASS_NAMES, MODEL_PATH
from transaction_engine import TransactionEngine


# =========================================================
# MODEL SETTINGS
# =========================================================

CONFIDENCE = 0.25
IOU = 0.50
IMAGE_SIZE = 640


# =========================================================
# DEVICE
# =========================================================

def get_device():

    if torch.backends.mps.is_available():

        return "mps"

    return "cpu"


# =========================================================
# PRODUCT NAME
# =========================================================

def format_product(
    class_id: int,
) -> str:

    return CLASS_NAMES.get(
        class_id,
        f"class_{class_id}",
    ).capitalize()


# =========================================================
# EXTRACT TRACKED DETECTIONS
# =========================================================

def extract_detections(
    result,
) -> list[dict]:

    detections = []

    if result.boxes is None:
        return detections

    boxes = result.boxes

    if len(boxes) == 0:
        return detections

    classes = (
        boxes.cls
        .cpu()
        .numpy()
        .astype(int)
    )

    confidences = (
        boxes.conf
        .cpu()
        .numpy()
    )

    if boxes.id is not None:

        track_ids = (
            boxes.id
            .cpu()
            .numpy()
            .astype(int)
        )

    else:

        track_ids = [
            None
            for _ in range(len(boxes))
        ]

    for class_id, confidence, track_id in zip(
        classes,
        confidences,
        track_ids,
    ):

        detections.append(
            {
                "track_id": (
                    int(track_id)
                    if track_id is not None
                    else None
                ),

                "class_id": int(
                    class_id
                ),

                "confidence": float(
                    confidence
                ),
            }
        )

    return detections


# =========================================================
# DRAW DETECTIONS
# =========================================================

def draw_detections(
    frame,
    result,
):

    boxes = result.boxes

    if boxes is None or len(boxes) == 0:

        return frame, 0

    xyxy = (
        boxes.xyxy
        .cpu()
        .numpy()
    )

    classes = (
        boxes.cls
        .cpu()
        .numpy()
        .astype(int)
    )

    confidences = (
        boxes.conf
        .cpu()
        .numpy()
    )

    if boxes.id is not None:

        track_ids = (
            boxes.id
            .cpu()
            .numpy()
            .astype(int)
        )

    else:

        track_ids = [
            None
            for _ in range(len(xyxy))
        ]

    detection_count = len(
        xyxy
    )

    for (
        box,
        class_id,
        confidence,
        track_id,
    ) in zip(
        xyxy,
        classes,
        confidences,
        track_ids,
    ):

        x1, y1, x2, y2 = [
            int(v)
            for v in box
        ]

        product = format_product(
            class_id
        )

        if track_id is not None:

            label = (
                f"{product} "
                f"#{track_id} "
                f"{confidence:.2f}"
            )

        else:

            label = (
                f"{product} "
                f"{confidence:.2f}"
            )

        # -----------------------------------------------
        # BOX
        # -----------------------------------------------

        cv2.rectangle(
            frame,
            (x1, y1),
            (x2, y2),
            (60, 180, 255),
            2,
        )

        # -----------------------------------------------
        # LABEL SIZE
        # -----------------------------------------------

        (
            text_width,
            text_height,
        ), baseline = cv2.getTextSize(
            label,
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            2,
        )

        text_y = max(
            y1 - 8,
            text_height + 5,
        )

        # -----------------------------------------------
        # LABEL BACKGROUND
        # -----------------------------------------------

        cv2.rectangle(
            frame,
            (
                x1,
                text_y
                - text_height
                - baseline
                - 4,
            ),
            (
                x1
                + text_width
                + 8,
                text_y + 2,
            ),
            (20, 25, 30),
            -1,
        )

        # -----------------------------------------------
        # LABEL
        # -----------------------------------------------

        cv2.putText(
            frame,
            label,
            (x1 + 4, text_y - 3),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )

    return (
        frame,
        detection_count,
    )


# =========================================================
# TOP OVERLAY
# =========================================================

def draw_system_overlay(
    frame,
    video_name: str,
    device: str,
    detection_count: int,
):

    height, width = (
        frame.shape[:2]
    )

    cv2.rectangle(
        frame,
        (0, 0),
        (width, 48),
        (15, 18, 22),
        -1,
    )

    title = (
        "SMARTCART | YOLO26n + ByteTrack"
    )

    cv2.putText(
        frame,
        title,
        (15, 20),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (245, 245, 245),
        2,
        cv2.LINE_AA,
    )

    info = (
        f"{video_name} | "
        f"Device: {device.upper()} | "
        f"Detections: {detection_count}"
    )

    cv2.putText(
        frame,
        info,
        (15, 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.40,
        (180, 190, 200),
        1,
        cv2.LINE_AA,
    )

    return frame


# =========================================================
# TRANSACTION OVERLAY
# =========================================================

def draw_transaction_event(
    frame,
    event: Optional[dict],
):

    if event is None:

        return frame

    height, width = (
        frame.shape[:2]
    )

    action = event.get(
        "event",
        "EVENT",
    )

    product_class = event.get(
        "product_class"
    )

    track_id = event.get(
        "track_id"
    )

    if product_class is None:

        return frame

    product = format_product(
        product_class
    )

    message = (
        f"{action} {product} "
        f" | Track #{track_id}"
    )

    box_height = 44

    cv2.rectangle(
        frame,
        (
            0,
            height - box_height,
        ),
        (
            width,
            height,
        ),
        (20, 45, 30),
        -1,
    )

    cv2.putText(
        frame,
        message,
        (
            15,
            height - 14,
        ),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (230, 255, 235),
        2,
        cv2.LINE_AA,
    )

    return frame


# =========================================================
# MJPEG GENERATOR
# =========================================================

def generate_mjpeg(
    video_path: str,
    event_callback: Optional[
        Callable[[dict], None]
    ] = None,
):

    video_path = Path(
        video_path
    )

    if not video_path.exists():

        raise FileNotFoundError(
            f"Video not found: {video_path}"
        )

    print()
    print("=" * 70)
    print("SMARTCART CV ENGINE")
    print("=" * 70)
    print(
        f"VIDEO : {video_path.name}"
    )
    print(
        f"MODEL : {MODEL_PATH}"
    )
    print("=" * 70)

    device = get_device()

    print(
        f"[CV] Device: {device}"
    )

    print(
        "[CV] Loading YOLO model..."
    )

    model = YOLO(
        str(MODEL_PATH)
    )

    print(
        "[CV] Model loaded."
    )

    print(
        f"[CV] Classes: {model.names}"
    )

    transaction_engine = (
        TransactionEngine()
    )

    cap = cv2.VideoCapture(
        str(video_path)
    )

    if not cap.isOpened():

        raise RuntimeError(
            f"Could not open video: "
            f"{video_path}"
        )

    fps = cap.get(
        cv2.CAP_PROP_FPS
    )

    if not fps or fps <= 0:

        fps = 25.0

    frame_delay = 1.0 / fps

    frame_number = 0

    last_transaction_event = None

    event_display_until = 0.0

    try:

        while True:

            loop_start = (
                time.perf_counter()
            )

            success, frame = (
                cap.read()
            )

            if not success:

                break

            video_time = (
                frame_number / fps
            )

            frame_number += 1

            # -------------------------------------------------
            # YOLO + BYTETRACK
            # -------------------------------------------------

            results = model.track(
                frame,
                persist=True,
                tracker="bytetrack.yaml",
                conf=CONFIDENCE,
                iou=IOU,
                imgsz=IMAGE_SIZE,
                device=device,
                verbose=False,
            )

            result = results[0]

            # -------------------------------------------------
            # EXTRACT DETECTIONS
            # -------------------------------------------------

            detections = (
                extract_detections(
                    result
                )
            )

            # -------------------------------------------------
            # TRANSACTION ENGINE
            # -------------------------------------------------

            events = (
                transaction_engine.update(
                    detections,
                    video_time,
                )
            )

            for event in events:

                print(
                    "[TX] Event generated:",
                    event,
                )

                if event_callback is not None:

                    try:

                        event_callback(
                            event
                        )

                    except Exception as exc:

                        print(
                            "[TX] "
                            f"Callback failed: "
                            f"{exc}"
                        )

                last_transaction_event = (
                    event
                )

                event_display_until = (
                    video_time + 1.5
                )

            # -------------------------------------------------
            # DRAW DETECTIONS
            # -------------------------------------------------

            frame, detection_count = (
                draw_detections(
                    frame,
                    result,
                )
            )

            # -------------------------------------------------
            # TOP INFORMATION
            # -------------------------------------------------

            frame = (
                draw_system_overlay(
                    frame,
                    video_path.name,
                    device,
                    detection_count,
                )
            )

            # -------------------------------------------------
            # TRANSACTION INFORMATION
            # -------------------------------------------------

            if (
                last_transaction_event
                is not None
                and
                video_time
                <= event_display_until
            ):

                frame = (
                    draw_transaction_event(
                        frame,
                        last_transaction_event,
                    )
                )

            # -------------------------------------------------
            # JPEG
            # -------------------------------------------------

            success, encoded = (
                cv2.imencode(
                    ".jpg",
                    frame,
                    [
                        int(
                            cv2.IMWRITE_JPEG_QUALITY
                        ),
                        85,
                    ],
                )
            )

            if not success:

                continue

            frame_bytes = (
                encoded.tobytes()
            )

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Cache-Control: no-cache\r\n"
                b"\r\n"
                + frame_bytes
                + b"\r\n"
            )

            # -------------------------------------------------
            # REAL-TIME PACING
            # -------------------------------------------------

            elapsed = (
                time.perf_counter()
                - loop_start
            )

            remaining = (
                frame_delay
                - elapsed
            )

            if remaining > 0:

                time.sleep(
                    remaining
                )

    finally:

        cap.release()

        print(
            "[CV] Video session ended: "
            f"{video_path.name}"
        )
