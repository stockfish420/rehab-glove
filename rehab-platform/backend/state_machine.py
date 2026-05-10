"""Repetition state machine for fused sensor and optical measurements."""

import time
from models import RepKPI


REST = "REST"
FLEXION = "FLEXION"
EXTENSION = "EXTENSION"


class RepStateMachine:
    def __init__(self, flex_threshold: float = 40.0, rest_threshold: float = 15.0) -> None:
        self.flex_threshold = flex_threshold
        self.rest_threshold = rest_threshold
        self.reset()

    @property
    def current_state(self) -> str:
        return self._state

    @property
    def rep_count(self) -> int:
        return self._rep_count

    def reset(self) -> None:
        self._state = REST
        self._rep_count = 0
        self._flex_candidate_frames = 0
        self._last_optical_angle: float | None = None
        self._reset_rep_accumulators()

    def update(
        self,
        optical_angle: float | None,
        sensor_angle: float,
        pressure: float,
    ) -> RepKPI | None:
        if optical_angle is None:
            return None

        completed_rep: RepKPI | None = None

        if self._state == REST:
            if optical_angle > self.flex_threshold:
                self._flex_candidate_frames += 1
            else:
                self._flex_candidate_frames = 0

            if self._flex_candidate_frames >= 3:
                self._state = FLEXION
                self._reset_rep_accumulators()
                self._record_flexion_sample(optical_angle, sensor_angle, pressure)

        elif self._state == FLEXION:
            self._record_flexion_sample(optical_angle, sensor_angle, pressure)

            if (
                self._last_optical_angle is not None
                and optical_angle < self._last_optical_angle
            ):
                self._state = EXTENSION

        elif self._state == EXTENSION:
            if optical_angle <= self.rest_threshold:
                completed_rep = self._complete_rep()
                self._state = REST
                self._flex_candidate_frames = 0
                self._reset_rep_accumulators()

        self._last_optical_angle = optical_angle
        return completed_rep

    def _record_flexion_sample(
        self,
        optical_angle: float,
        sensor_angle: float,
        pressure: float,
    ) -> None:
        self._peak_optical_angle = max(self._peak_optical_angle, optical_angle)
        self._peak_sensor_angle = max(self._peak_sensor_angle, sensor_angle)
        self._pressure_total += pressure
        self._pressure_samples += 1

    def _complete_rep(self) -> RepKPI:
        self._rep_count += 1

        average_pressure = 0.0
        if self._pressure_samples > 0:
            average_pressure = self._pressure_total / self._pressure_samples

        return RepKPI(
            rep_number=self._rep_count,
            angle_sensor=self._peak_sensor_angle,
            angle_optical=self._peak_optical_angle,
            accuracy_delta=abs(self._peak_sensor_angle - self._peak_optical_angle),
            pressure=average_pressure,
            timestamp=time.time(),
        )

    def _reset_rep_accumulators(self) -> None:
        self._peak_sensor_angle = 0.0
        self._peak_optical_angle = 0.0
        self._pressure_total = 0.0
        self._pressure_samples = 0
