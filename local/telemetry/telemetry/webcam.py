"""Section 2 (Opt-In): Local 20Hz webcam oculometrics, facial action & rPPG HR.

Processes frames strictly in memory via OpenCV + MediaPipe Face Mesh and discards
images immediately—only anonymized scalar metrics are queued to SQLite.
"""

from __future__ import annotations

import collections
import logging
import math
import threading
import time
from typing import Sequence

from telemetry.db import BatchWriter

log = logging.getLogger(__name__)

# MediaPipe 468-landmark indices
LEFT_EYE_IDX = (33, 160, 158, 133, 153, 144)
RIGHT_EYE_IDX = (362, 385, 387, 263, 373, 380)
MOUTH_IDX = (61, 81, 311, 291, 402, 178)
NOSE_TIP_IDX = 1
CHIN_IDX = 152
FOREHEAD_IDX = 10
# Upper lid & brow landmarks for lid-tightening proxy (Kong et al. 2020)
LEFT_BROW_IDX = 105
LEFT_UPPER_LID_IDX = 159
RIGHT_BROW_IDX = 334
RIGHT_UPPER_LID_IDX = 386

BLINK_MIN_MS = 50.0
BLINK_MAX_MS = 5000.0
RPPG_MIN_BPM = 45.0
RPPG_MAX_BPM = 150.0
RPPG_WINDOW_S = 30.0  # Peer-reviewed 25-45s window (Behavior Research Methods 2024)
MIN_FRAME_LUMA = 40.0  # Reject dim/dark frames (0-255 grayscale)
MAX_HEAD_YAW = 0.35    # Reject extreme side-turns (second monitor)
MIN_FACE_HEIGHT = 0.15  # ~1.5m proximity perimeter on a laptop webcam


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def eye_aspect_ratio(pts: Sequence[tuple[float, float]]) -> float:
    """Compute Eye Aspect Ratio (EAR) from 6 ordered eye landmarks."""
    horiz = _dist(pts[0], pts[3])
    if horiz < 1e-9:
        return 0.0
    return (_dist(pts[1], pts[5]) + _dist(pts[2], pts[4])) / (2.0 * horiz)


def mouth_aspect_ratio(pts: Sequence[tuple[float, float]]) -> float:
    """Compute Mouth Aspect Ratio (MAR) from 6 ordered mouth landmarks."""
    horiz = _dist(pts[0], pts[3])
    if horiz < 1e-9:
        return 0.0
    return (_dist(pts[1], pts[5]) + _dist(pts[2], pts[4])) / (2.0 * horiz)


def head_pitch_proxy(
    forehead: tuple[float, float],
    nose: tuple[float, float],
    chin: tuple[float, float],
) -> float:
    """Normalized vertical nose position between forehead and chin (nodding proxy)."""
    face_h = abs(chin[1] - forehead[1])
    if face_h < 1e-9:
        return 0.0
    return (nose[1] - forehead[1]) / face_h


def lid_tightening_ratio(landmarks: Sequence[tuple[float, float]]) -> float:
    """Brow-to-upper-lid distance normalized by face height (smaller = tighter lids)."""
    face_h = abs(landmarks[CHIN_IDX][1] - landmarks[FOREHEAD_IDX][1])
    if face_h < 1e-9:
        return 0.0
    left_gap = _dist(landmarks[LEFT_BROW_IDX], landmarks[LEFT_UPPER_LID_IDX])
    right_gap = _dist(landmarks[RIGHT_BROW_IDX], landmarks[RIGHT_UPPER_LID_IDX])
    return ((left_gap + right_gap) / 2.0) / face_h


def head_yaw_proxy(landmarks: Sequence[tuple[float, float]]) -> float:
    """Normalized horizontal offset of nose from eye midpoint (0 = straight ahead)."""
    left_x = landmarks[LEFT_EYE_IDX[0]][0]
    right_x = landmarks[RIGHT_EYE_IDX[3]][0]
    eye_span = abs(right_x - left_x)
    if eye_span < 1e-9:
        return 1.0
    mid_x = (left_x + right_x) / 2.0
    return abs(landmarks[NOSE_TIP_IDX][0] - mid_x) / eye_span


def estimate_rppg_hr_bpm(
    green_series: Sequence[float],
    sample_hz: float = 20.0,
) -> float | None:
    """Estimate mean heart rate (bpm) from a 25-45s facial green-channel buffer."""
    n = len(green_series)
    if n < int(25.0 * sample_hz):
        return None

    mean_val = sum(green_series) / n
    centered = [x - mean_val for x in green_series]
    if max(abs(x) for x in centered) < 1e-6:
        return None

    # Evaluate DFT power across physiological HR band (45-150 bpm, step 1 bpm)
    best_bpm: float | None = None
    best_power = -1.0
    total_power = 0.0
    bins = list(range(int(RPPG_MIN_BPM), int(RPPG_MAX_BPM) + 1))
    for bpm in bins:
        freq_hz = bpm / 60.0
        omega = 2.0 * math.pi * freq_hz / sample_hz
        re = sum(centered[k] * math.cos(omega * k) for k in range(n))
        im = sum(centered[k] * math.sin(omega * k) for k in range(n))
        power = re * re + im * im
        total_power += power
        if power > best_power:
            best_power = power
            best_bpm = float(bpm)

    # Spectral SNR gate: reject flat/noisy spectra caused by lighting flicker or motion
    mean_power = total_power / max(1, len(bins))
    if mean_power < 1e-12 or (best_power / mean_power) < 3.0:
        return None
    return best_bpm


class WebcamOculometricsCollector:
    """Opt-in 20Hz webcam sampler writing anonymized oculometrics & rPPG HR at ~1Hz."""

    def __init__(
        self,
        writer: BatchWriter,
        sample_hz: float = 20.0,
        emit_interval_s: float = 1.0,
        ear_closed_threshold: float = 0.20,
        camera_index: int = 0,
    ) -> None:
        self.writer = writer
        self.sample_hz = sample_hz
        self.sample_interval_s = 1.0 / sample_hz
        self.emit_interval_s = emit_interval_s
        self.ear_closed_threshold = ear_closed_threshold
        self.camera_index = camera_index

        self._closed_start_perf: float | None = None
        self._last_emit_perf: float | None = None
        self._last_green_perf: float | None = None
        self._frames_since_emit: int = 0
        self._closed_frames_since_emit: int = 0
        self._bad_frames_since_emit: int = 0
        self._green_buf: collections.deque[float] = collections.deque(
            maxlen=int(RPPG_WINDOW_S * sample_hz)
        )
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._burst_lock = threading.Lock()
        self._last_burst_ts: float = 0.0

    def record_bad_frame(self) -> None:
        """Mark a frame as unusable (dim lighting, no face detected, or extreme yaw)."""
        self._bad_frames_since_emit += 1
        self._closed_start_perf = None

    def process_landmarks(
        self,
        landmarks: Sequence[tuple[float, float]],
        green_mean: float | None = None,
        perf_now: float | None = None,
        wall_now: float | None = None,
    ) -> tuple[float, float, float, float, float, int, float | None, float | None] | None:
        """Process one 20Hz frame; emits to SQLite on blink completion or every emit_interval_s."""
        t_perf = perf_now if perf_now is not None else time.perf_counter()
        t_wall = wall_now if wall_now is not None else time.time()

        left_ear = eye_aspect_ratio([landmarks[i] for i in LEFT_EYE_IDX])
        right_ear = eye_aspect_ratio([landmarks[i] for i in RIGHT_EYE_IDX])
        ear = (left_ear + right_ear) / 2.0
        mar = mouth_aspect_ratio([landmarks[i] for i in MOUTH_IDX])
        pitch = head_pitch_proxy(
            landmarks[FOREHEAD_IDX], landmarks[NOSE_TIP_IDX], landmarks[CHIN_IDX]
        )
        lid_tight = lid_tightening_ratio(landmarks)
        is_closed = int(ear < self.ear_closed_threshold)
        self._frames_since_emit += 1
        self._closed_frames_since_emit += is_closed

        # Blink duration state machine (closed -> open)
        blink_duration_ms: float | None = None
        if is_closed:
            if self._closed_start_perf is None:
                self._closed_start_perf = t_perf
        elif self._closed_start_perf is not None:
            dur_ms = (t_perf - self._closed_start_perf) * 1000.0
            self._closed_start_perf = None
            if BLINK_MIN_MS <= dur_ms <= BLINK_MAX_MS:
                blink_duration_ms = round(dur_ms, 2)

        if green_mean is not None:
            if self._last_green_perf is not None and (t_perf - self._last_green_perf) > 2.0:
                self._green_buf.clear()
            self._green_buf.append(green_mean)
            self._last_green_perf = t_perf

        should_emit = (
            blink_duration_ms is not None
            or self._last_emit_perf is None
            or (t_perf - self._last_emit_perf) >= self.emit_interval_s
        )
        if not should_emit:
            return None

        # Exact 20Hz PERCLOS fraction and valid-frame quality ratio since last emit
        total_attempts = self._frames_since_emit + self._bad_frames_since_emit
        valid_ratio = self._frames_since_emit / max(1, total_attempts)
        closed_ratio = self._closed_frames_since_emit / max(1, self._frames_since_emit)
        self._frames_since_emit = 0
        self._closed_frames_since_emit = 0
        self._bad_frames_since_emit = 0

        rppg_hr = estimate_rppg_hr_bpm(self._green_buf, self.sample_hz)
        self._last_emit_perf = t_perf
        row = (
            t_wall,
            round(ear, 4),
            round(mar, 4),
            round(pitch, 4),
            round(lid_tight, 4),
            round(closed_ratio, 4),
            blink_duration_ms,
            round(rppg_hr, 1) if rppg_hr is not None else None,
            round(valid_ratio, 4),
        )
        self.writer.enqueue("raw_webcam", row)
        return row

    def trigger_burst(self, duration_s: float = 60.0, cooldown_s: float = 600.0) -> bool:
        """Start a non-blocking on-demand confirmation burst if cooldown has elapsed."""
        now = time.time()
        with self._burst_lock:
            if self._thread is not None and self._thread.is_alive():
                return False
            if (now - self._last_burst_ts) < cooldown_s:
                return False
            self._last_burst_ts = now
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run,
                args=(duration_s,),
                name="webcam-burst",
                daemon=True,
            )
            self._thread.start()
            return True

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)

    def _run(self, max_duration_s: float | None = None) -> None:
        try:
            import cv2
            import mediapipe as mp
        except ImportError:
            log.warning(
                "Webcam collector disabled: install optional dependencies with "
                "`pip install -e '.[webcam]'` (opencv-python, mediapipe)."
            )
            return

        cap = cv2.VideoCapture(self.camera_index)
        if not cap.isOpened():
            log.warning("Could not open webcam (index=%d).", self.camera_index)
            return

        face_mesh = mp.solutions.face_mesh.FaceMesh(
            max_num_faces=3,
            refine_landmarks=False,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        deadline = (time.perf_counter() + max_duration_s) if max_duration_s is not None else None
        if max_duration_s is not None:
            log.info("Webcam confirmation burst started (%ds).", int(max_duration_s))
        try:
            while not self._stop_event.wait(self.sample_interval_s):
                if deadline is not None and time.perf_counter() >= deadline:
                    break
                ok, frame = cap.read()
                if not ok:
                    self.record_bad_frame()
                    continue
                # Reject dim/dark frames before landmark extraction
                if float(frame.mean()) < MIN_FRAME_LUMA:
                    self.record_bad_frame()
                    continue
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                res = face_mesh.process(rgb)
                if not res.multi_face_landmarks:
                    self.record_bad_frame()
                    continue
                # Keep only faces inside the ~1.5m proximity perimeter; ignore if 0 or >= 2
                in_range = [
                    [(lm.x, lm.y) for lm in fl.landmark]
                    for fl in res.multi_face_landmarks
                    if abs(fl.landmark[CHIN_IDX].y - fl.landmark[FOREHEAD_IDX].y) >= MIN_FACE_HEIGHT
                ]
                if len(in_range) != 1:
                    self.record_bad_frame()
                    continue
                pts = in_range[0]
                if head_yaw_proxy(pts) > MAX_HEAD_YAW:
                    self.record_bad_frame()
                    continue
                # Forehead ROI green-channel mean for contactless rPPG HR
                h, w, _ = frame.shape
                fx, fy = int(pts[FOREHEAD_IDX][0] * w), int(pts[FOREHEAD_IDX][1] * h)
                roi = frame[max(0, fy - 10) : min(h, fy + 10), max(0, fx - 15) : min(w, fx + 15)]
                green_mean = float(roi[:, :, 1].mean()) if roi.size > 0 else None
                self.process_landmarks(pts, green_mean=green_mean)
        finally:
            face_mesh.close()
            cap.release()
            if max_duration_s is not None:
                log.info("Webcam confirmation burst finished.")
