"""Threaded webcam hand tracking and optical ROM estimation."""

import cv2
import mediapipe as mp
import numpy as np
import os
import threading

from mediapipe.tasks.python import vision
from mediapipe.tasks.python.core.base_options import BaseOptions


WRIST = 0
MCP = 9
PIP = 10
DIP = 11
TIP = 12


class VisionEngine:
    def __init__(self, camera_index: int = 0) -> None:
        self.camera_index = camera_index
        self._capture: cv2.VideoCapture | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._latest_frame: np.ndarray | None = None
        self._angle: float | None = None
        self._is_running = False
        self._landmarker_model_path = os.getenv(
            "HAND_LANDMARKER_MODEL",
            os.path.join(os.path.dirname(__file__), "assets", "hand_landmarker.task"),
        )
        self._using_solutions = hasattr(mp, "solutions")
        self._mp_hands = mp.solutions.hands if self._using_solutions else None
        self._mp_drawing = mp.solutions.drawing_utils if self._using_solutions else None

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._is_running

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._processing_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2)

        self._release_camera()
        self._set_running(False)

    def get_latest_frame(self) -> np.ndarray | None:
        with self._lock:
            if self._latest_frame is None:
                return None
            return self._latest_frame.copy()

    def get_angle(self) -> float | None:
        with self._lock:
            return self._angle

    def _processing_loop(self) -> None:
        self._capture = cv2.VideoCapture(self.camera_index)
        self._capture.set(cv2.CAP_PROP_FPS, 30)

        if not self._capture.isOpened():
            self._set_running(False)
            self._release_camera()
            return

        self._set_running(True)

        if self._using_solutions:
            with self._mp_hands.Hands(
                static_image_mode=False,
                max_num_hands=1,
                model_complexity=1,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            ) as hands:
                self._run_frame_loop(hands)
        elif os.path.exists(self._landmarker_model_path):
            options = vision.HandLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=self._landmarker_model_path),
                running_mode=vision.RunningMode.IMAGE,
                num_hands=1,
                min_hand_detection_confidence=0.5,
                min_hand_presence_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            with vision.HandLandmarker.create_from_options(options) as landmarker:
                self._run_frame_loop(landmarker)
        else:
            self._run_raw_frame_loop()

        self._release_camera()
        self._set_running(False)

    def _run_frame_loop(self, detector: object) -> None:
        while not self._stop_event.is_set():
            ok, frame = self._capture.read()
            if not ok:
                continue

            annotated_frame, angle = self._process_frame(frame, detector)

            with self._lock:
                self._latest_frame = annotated_frame
                self._angle = angle

    def _run_raw_frame_loop(self) -> None:
        while not self._stop_event.is_set():
            ok, frame = self._capture.read()
            if not ok:
                continue

            with self._lock:
                self._latest_frame = frame
                self._angle = None

    def _process_frame(self, frame: np.ndarray, detector: object) -> tuple[np.ndarray, float | None]:
        if self._using_solutions:
            return self._process_frame_with_solutions(frame, detector)

        return self._process_frame_with_tasks(frame, detector)

    def _process_frame_with_solutions(
        self,
        frame: np.ndarray,
        hands: object,
    ) -> tuple[np.ndarray, float | None]:
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = hands.process(rgb_frame)

        if not results.multi_hand_landmarks:
            return frame, None

        annotated_frame = frame.copy()
        hand_landmarks = results.multi_hand_landmarks[0]
        angle = self._calculate_pip_angle(hand_landmarks.landmark)

        self._mp_drawing.draw_landmarks(
            annotated_frame,
            hand_landmarks,
            self._mp_hands.HAND_CONNECTIONS,
        )

        if angle is not None:
            cv2.putText(
                annotated_frame,
                f"Optical: {angle:.1f} deg",
                (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                (0, 255, 0),
                2,
                cv2.LINE_AA,
            )

        return annotated_frame, angle

    def _process_frame_with_tasks(
        self,
        frame: np.ndarray,
        landmarker: object,
    ) -> tuple[np.ndarray, float | None]:
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        result = landmarker.detect(mp_image)

        if not result.hand_landmarks:
            return frame, None

        annotated_frame = frame.copy()
        hand_landmarks = result.hand_landmarks[0]
        angle = self._calculate_pip_angle(hand_landmarks)
        self._draw_task_landmarks(annotated_frame, hand_landmarks)

        if angle is not None:
            cv2.putText(
                annotated_frame,
                f"Optical: {angle:.1f} deg",
                (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                (0, 255, 0),
                2,
                cv2.LINE_AA,
            )

        return annotated_frame, angle

    def _draw_task_landmarks(self, frame: np.ndarray, landmarks: object) -> None:
        height, width = frame.shape[:2]
        points = [
            (int(landmark.x * width), int(landmark.y * height))
            for landmark in landmarks
        ]

        for connection in vision.HandLandmarksConnections.HAND_CONNECTIONS:
            start = points[connection.start]
            end = points[connection.end]
            cv2.line(frame, start, end, (80, 220, 255), 2, cv2.LINE_AA)

        for point in points:
            cv2.circle(frame, point, 3, (0, 255, 0), -1, cv2.LINE_AA)

    def _calculate_pip_angle(self, landmarks: object) -> float | None:
        mcp = self._landmark_to_array(landmarks[MCP])
        pip = self._landmark_to_array(landmarks[PIP])
        dip = self._landmark_to_array(landmarks[DIP])

        vec_mcp_to_pip = pip - mcp
        vec_pip_to_dip = dip - pip

        norm_a = np.linalg.norm(vec_mcp_to_pip)
        norm_b = np.linalg.norm(vec_pip_to_dip)
        if norm_a == 0 or norm_b == 0:
            return None

        cos_theta = np.dot(vec_mcp_to_pip, vec_pip_to_dip) / (norm_a * norm_b)
        cos_theta = np.clip(cos_theta, -1.0, 1.0)
        flexion_angle = np.degrees(np.arccos(cos_theta))

        return float(flexion_angle)

    def _landmark_to_array(self, landmark: object) -> np.ndarray:
        return np.array([landmark.x, landmark.y, landmark.z], dtype=np.float32)

    def _set_running(self, running: bool) -> None:
        with self._lock:
            self._is_running = running

    def _release_camera(self) -> None:
        capture = self._capture
        self._capture = None

        if capture is not None:
            capture.release()
