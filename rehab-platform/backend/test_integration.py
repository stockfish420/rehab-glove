"""Synthetic integration test for the rehab backend pipeline."""

import asyncio
import math

import numpy as np

from llm_worker import LLMWorker
from state_machine import RepStateMachine


SAMPLE_HZ = 20
SAMPLE_DT_SECONDS = 1 / SAMPLE_HZ
SESSION_SECONDS = 30
PERIOD_SECONDS = 3
PRESSURE_NEWTONS = 5.0


class MockSerialReader:
    def get_angle(self, elapsed_seconds: float) -> float:
        return 40.0 * (1.0 - math.cos((2.0 * math.pi * elapsed_seconds) / PERIOD_SECONDS))

    def get_pressure(self) -> float:
        return PRESSURE_NEWTONS


class MockVisionEngine:
    def __init__(self, rng: np.random.Generator) -> None:
        self.rng = rng

    def get_angle(self, sensor_angle: float) -> float:
        noisy_angle = sensor_angle + self.rng.normal(0.0, 5.0)
        return float(np.clip(noisy_angle, 0.0, 90.0))


def print_kpi_table(kpis) -> None:
    print("\nDetected Rep KPIs")
    print("-" * 72)
    print(f"{'Rep':>4} | {'Optical':>10} | {'Sensor':>10} | {'Delta':>10} | {'Pressure':>10}")
    print("-" * 72)

    for kpi in kpis:
        print(
            f"{kpi.rep_number:>4} | "
            f"{kpi.angle_optical:>8.1f}deg | "
            f"{kpi.angle_sensor:>8.1f}deg | "
            f"{kpi.accuracy_delta:>8.1f}deg | "
            f"{kpi.pressure:>9.2f}N"
        )

    print("-" * 72)


async def main() -> None:
    rng = np.random.default_rng(seed=7)
    serial_reader = MockSerialReader()
    vision_engine = MockVisionEngine(rng)
    state_machine = RepStateMachine()
    kpis = []

    total_samples = int(SESSION_SECONDS * SAMPLE_HZ)

    for sample_index in range(total_samples):
        elapsed_seconds = sample_index * SAMPLE_DT_SECONDS
        sensor_angle = serial_reader.get_angle(elapsed_seconds)
        optical_angle = vision_engine.get_angle(sensor_angle)
        pressure = serial_reader.get_pressure()

        completed_kpi = state_machine.update(optical_angle, sensor_angle, pressure)
        if completed_kpi is not None:
            kpis.append(completed_kpi)

    print_kpi_table(kpis)

    assert len(kpis) >= 8, f"Expected at least 8 reps, detected {len(kpis)}"

    average_delta = sum(kpi.accuracy_delta for kpi in kpis) / len(kpis)
    print(f"\nAverage accuracy delta: {average_delta:.2f}deg")
    assert average_delta < 10.0, f"Expected average delta < 10deg, got {average_delta:.2f}deg"

    llm_worker = LLMWorker()
    if not llm_worker.is_available():
        print("\nLLM summary skipped: Ollama is unavailable.")
        return

    print("\nLLM Session Summary")
    print("-" * 72)
    summary = await llm_worker.get_session_summary(kpis)
    print(summary)


if __name__ == "__main__":
    asyncio.run(main())
