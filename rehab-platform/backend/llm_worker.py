"""Async-safe Ollama coaching worker."""

import asyncio
import csv
import io
import json
import logging
import os
import statistics

import ollama
from models import RepKPI


LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "45"))
OLLAMA_HOST = "http://localhost:11434"
TIMEOUT_FALLBACK = "Analysis unavailable - LLM timeout."
logger = logging.getLogger(__name__)

LIVE_COACHING_PROMPT = """
You are ARIA, a clinical hand rehabilitation coaching assistant.
A patient has just completed one repetition. Analyse the data below
and respond with EXACTLY one sentence of actionable coaching feedback.
Focus on whichever metric is furthest from ideal.
Do not greet the user. Do not explain what you are doing.
Do not use LaTeX, formulas, markdown, or special formatting.
Output the single sentence only.

Rep Data:
- Flexion Angle Achieved: {vision_angle:.1f} deg (target: >60 deg)
- Peak Grip Pressure: {peak_pressure}/100 (target: 60-80)
- Sensor-Vision Accuracy Delta: {bend_accuracy_delta:.1f} deg (target: <10 deg)
- Rep Number: {rep_count}
- Session Elapsed: {elapsed_seconds}s
"""

ANOMALY_DETECTION_PROMPT = """
You are ARIA, a clinical rehabilitation data analyst.
Evaluate the following rep data against the thresholds provided.
If any threshold is breached, output a single flag entry in this
exact format and nothing else:

Rep {rep_count}: [metric name] ([observed value]) - [one-phrase clinical reason]

If no threshold is breached, output exactly: NO_FLAG
Do not use LaTeX, formulas, markdown, or special formatting.

Thresholds:
- Pressure spike: >90/100
- Angle deficit: <50 deg
- Accuracy delta: >15 deg
- Cadence drop: >30% below session mean

Rep Data:
- Rep Number: {rep_count}
- Peak Pressure: {peak_pressure}/100
- Flexion Angle: {vision_angle:.1f} deg
- Accuracy Delta: {bend_accuracy_delta:.1f} deg
- Rep Duration: {rep_duration:.2f}s
- Session Mean Rep Duration: {session_mean_duration:.2f}s
"""

POST_SESSION_SUMMARY_PROMPT = """
You are ARIA, a clinical rehabilitation AI generating a formal
post-session patient report. Analyse the session CSV data provided
and generate EXACTLY three bullet points covering the three categories
below. Each bullet must begin with the bold category label exactly
as shown. Each bullet must be 2-3 sentences. Use clinical language.
Do not add any text before or after the three bullets.
Do not use LaTeX, formulas, code fences, or mathematical notation.

Categories:
* **Consistency:** - analyse rep cadence, fatigue onset, and recommended session length adjustment
* **Pressure Trend:** - analyse grip pressure trajectory, compensatory patterns, and recommended drills
* **Angle Accuracy:** - analyse vision-sensor correlation quality, motor control, and endurance

Session CSV:
{csv_data}

Session Summary Stats:
- Total Reps: {total_reps}
- Session Duration: {duration_str}
- Avg Flexion Angle: {avg_angle:.1f} deg
- Avg Peak Pressure: {avg_pressure}/100
- Avg Accuracy Delta: {mean_delta:.1f} deg
- Flag Count: {flag_count}
"""

OBSERVATIONS_PROMPT = """
You are ARIA, a clinical rehabilitation analyst writing a formal session report.
Write exactly four short paragraphs, each starting with these exact labels:
Consistency:
Angle Accuracy:
Pressure Application:
Sensor-Vision Correlation:

Use precise clinical language. Do not use bullet points, LaTeX, formulas, or code fences.

Session Data:
- Total Reps: {total_reps}
- Rep Durations: {duration_series}
- Mean Rep Duration: {mean_duration:.2f}s
- Avg Flexion Angle: {avg_angle:.1f} deg
- Min Angle: {min_angle:.1f} deg
- Max Angle: {max_angle:.1f} deg
- Angle Std Dev: {angle_std:.1f} deg
- Avg Peak Pressure: {avg_pressure}/100
- Reps Within Pressure Band 60-80: {compliant_reps} of {total_reps}
- Pressure Spike Reps >90: {spike_reps_list}
- Mean Accuracy Delta: {mean_delta:.1f} deg
- Max Delta: {max_delta:.1f} deg
- Delta Std Dev: {delta_std:.1f} deg
- Fatigue Onset Rep: {fatigue_onset_rep}
"""

TREND_CLASSIFICATION_PROMPT = """
You are ARIA, a clinical data classifier. Classify the trend for
each of the four indicators below based on the session data provided.
Output ONLY a JSON array with exactly four objects. No explanation,
no markdown, no code fences. Raw JSON only.

Each object must have exactly these keys:
"indicator": string
"trend": string describing the pattern in 3-5 words
"direction": string

Session Data:
- Angle values per rep: {angle_series}
- Pressure values per rep: {pressure_series}
- Delta values per rep: {delta_series}
- Rep durations per rep: {duration_series}
"""

RECOMMENDATIONS_PROMPT = """
You are ARIA, a clinical rehabilitation AI. Based on the session
analysis below, generate EXACTLY four numbered recommendations for
the patient's next session and recovery plan. Each recommendation
must be one sentence, actionable, and specific. Bold the key action
phrase at the start of each item. Do not add any text before or
after the four numbered items.
Do not use LaTeX, formulas, code fences, or mathematical notation.

Session Analysis Summary:
- Fatigue onset detected at rep: {fatigue_onset_rep}
- Pressure spike count: {spike_count}
- Avg accuracy delta: {mean_delta:.1f} deg
- Delta exceeded threshold in final third: {delta_breach}
- Session flag count: {flag_count}
- Recommended max reps based on fatigue curve: {recommended_rep_cap}
"""


class LLMWorker:
    def __init__(self, model: str = "gemma4:e2b") -> None:
        self.model = model
        self._client = ollama.Client(host=OLLAMA_HOST)

    async def get_rep_critique(
        self,
        kpi: RepKPI,
        elapsed_seconds: int = 0,
    ) -> str:
        prompt = LIVE_COACHING_PROMPT.format(
            vision_angle=kpi.angle_optical,
            peak_pressure=self._pressure_score(kpi.pressure),
            bend_accuracy_delta=kpi.accuracy_delta,
            rep_count=kpi.rep_number,
            elapsed_seconds=elapsed_seconds,
        )
        return await self._chat("You are ARIA, a concise clinical hand rehabilitation coach.", prompt)

    async def get_anomaly_flag(
        self,
        kpi: RepKPI,
        rep_duration: float,
        session_mean_duration: float,
    ) -> str:
        prompt = ANOMALY_DETECTION_PROMPT.format(
            rep_count=kpi.rep_number,
            peak_pressure=self._pressure_score(kpi.pressure),
            vision_angle=kpi.angle_optical,
            bend_accuracy_delta=kpi.accuracy_delta,
            rep_duration=rep_duration,
            session_mean_duration=session_mean_duration,
        )
        return await self._chat("You are ARIA, a strict clinical anomaly classifier.", prompt)

    async def get_live_chat_response(self, message: str, context: dict[str, object]) -> str:
        system_prompt = (
            "You are ARIA, a physical therapy AI embedded in a live hand rehabilitation dashboard. "
            "Answer directly and clinically in 1-3 concise sentences. Use the provided live session "
            "context when relevant. Do not use LaTeX or formulas."
        )
        user_prompt = (
            f"Live context: state={context.get('state')}, rep_count={context.get('rep_count')}, "
            f"optical_angle={context.get('optical_angle')}, sensor_angle={context.get('sensor_angle')}, "
            f"pressure={context.get('pressure')}N. User asks: {message}"
        )
        return await self._chat(system_prompt, user_prompt)

    async def get_session_summary(
        self,
        all_kpis: list[RepKPI],
        flags: list[str] | None = None,
    ) -> str:
        flags = flags or []
        if not all_kpis:
            return (
                "* **Consistency:** No completed repetitions were recorded, so cadence and fatigue cannot be assessed.\n\n"
                "* **Pressure Trend:** No pressure samples were captured for compliant-band analysis.\n\n"
                "* **Angle Accuracy:** No paired vision-sensor rep data is available for correlation review."
            )

        stats = self._session_stats(all_kpis, flags)
        observations = await self._chat(
            "You are ARIA, a clinical rehabilitation observation writer.",
            OBSERVATIONS_PROMPT.format(**stats),
        )
        summary = await self._chat(
            "You are ARIA, a clinical rehabilitation report writer.",
            POST_SESSION_SUMMARY_PROMPT.format(**stats),
        )
        trends = await self._chat(
            "You are ARIA, a strict JSON-only clinical trend classifier.",
            TREND_CLASSIFICATION_PROMPT.format(**stats),
        )
        recommendations = await self._chat(
            "You are ARIA, a clinical rehabilitation recommendation engine.",
            RECOMMENDATIONS_PROMPT.format(**stats),
        )

        flags_block = "\n".join(flags) if flags else "NO_FLAG"
        return (
            f"Summary\n{summary.strip()}\n\n"
            f"Observations\n{observations.strip()}\n\n"
            f"Flags & Anomalies\n{flags_block}\n\n"
            f"Trend Indicators\n{trends.strip()}\n\n"
            f"Recommendations\n{recommendations.strip()}"
        )

    def is_available(self) -> bool:
        try:
            self._client.list()
        except Exception as exc:
            logger.warning("Ollama availability check failed: %s", exc)
            return False

        return True

    async def _chat(self, system_prompt: str, user_prompt: str) -> str:
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    self._client.chat,
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    stream=False,
                ),
                timeout=LLM_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            return TIMEOUT_FALLBACK
        except Exception as exc:
            logger.exception("Ollama chat request failed: %s", exc)
            return "Analysis unavailable - LLM request failed."

        if isinstance(response, dict):
            message = response.get("message", {})
            content = message.get("content", "").strip()
        else:
            message = getattr(response, "message", None)
            content = getattr(message, "content", "").strip()

        return self._clean_response(content) or "Analysis unavailable - empty LLM response."

    def _session_stats(self, kpis: list[RepKPI], flags: list[str]) -> dict[str, object]:
        total_reps = len(kpis)
        angles = [kpi.angle_optical for kpi in kpis]
        pressure_scores = [self._pressure_score(kpi.pressure) for kpi in kpis]
        deltas = [kpi.accuracy_delta for kpi in kpis]
        durations = self._rep_durations(kpis)
        mean_duration = statistics.mean(durations) if durations else 0.0
        fatigue_onset_rep = self._fatigue_onset_rep(kpis, durations)
        spike_reps = [kpi.rep_number for kpi, pressure in zip(kpis, pressure_scores) if pressure > 90]
        compliant_reps = sum(1 for pressure in pressure_scores if 60 <= pressure <= 80)
        final_third = deltas[-max(1, total_reps // 3):]
        delta_breach = "YES" if any(delta > 10 for delta in final_third) else "NO"
        recommended_rep_cap = fatigue_onset_rep if fatigue_onset_rep != "NONE" else total_reps

        return {
            "csv_data": self._session_csv(kpis, durations),
            "total_reps": total_reps,
            "duration_str": self._duration_str(kpis),
            "avg_angle": statistics.mean(angles),
            "min_angle": min(angles),
            "max_angle": max(angles),
            "angle_std": statistics.pstdev(angles) if len(angles) > 1 else 0.0,
            "avg_pressure": round(statistics.mean(pressure_scores)),
            "compliant_reps": compliant_reps,
            "spike_reps_list": spike_reps or "NONE",
            "mean_delta": statistics.mean(deltas),
            "max_delta": max(deltas),
            "delta_std": statistics.pstdev(deltas) if len(deltas) > 1 else 0.0,
            "flag_count": len(flags),
            "fatigue_onset_rep": fatigue_onset_rep,
            "spike_count": len(spike_reps),
            "delta_breach": delta_breach,
            "recommended_rep_cap": recommended_rep_cap,
            "mean_duration": mean_duration,
            "angle_series": [round(angle, 1) for angle in angles],
            "pressure_series": pressure_scores,
            "delta_series": [round(delta, 1) for delta in deltas],
            "duration_series": [round(duration, 2) for duration in durations],
        }

    def _session_csv(self, kpis: list[RepKPI], durations: list[float]) -> str:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["rep", "angle_optical_deg", "angle_sensor_deg", "pressure_100", "delta_deg", "duration_s"])
        for index, kpi in enumerate(kpis):
            writer.writerow(
                [
                    kpi.rep_number,
                    f"{kpi.angle_optical:.1f}",
                    f"{kpi.angle_sensor:.1f}",
                    self._pressure_score(kpi.pressure),
                    f"{kpi.accuracy_delta:.1f}",
                    f"{durations[index]:.2f}" if index < len(durations) else "0.00",
                ]
            )
        return output.getvalue().strip()

    def _rep_durations(self, kpis: list[RepKPI]) -> list[float]:
        if not kpis:
            return []
        durations = [0.0]
        for previous, current in zip(kpis, kpis[1:]):
            durations.append(max(0.0, current.timestamp - previous.timestamp))
        if len(durations) > 1:
            durations[0] = durations[1]
        return durations

    def _duration_str(self, kpis: list[RepKPI]) -> str:
        if len(kpis) < 2:
            return "under 1 minute"
        seconds = max(0.0, kpis[-1].timestamp - kpis[0].timestamp)
        minutes = int(seconds // 60)
        remaining_seconds = int(seconds % 60)
        return f"{minutes}m {remaining_seconds}s"

    def _fatigue_onset_rep(self, kpis: list[RepKPI], durations: list[float]) -> str | int:
        if len(durations) < 4:
            return "NONE"
        mean_duration = statistics.mean(durations)
        for kpi, duration in zip(kpis, durations):
            if mean_duration > 0 and duration > mean_duration * 1.3:
                return kpi.rep_number
        return "NONE"

    def _pressure_score(self, pressure_newtons: float) -> int:
        return round(max(0.0, min(10.0, pressure_newtons)) * 10)

    def _clean_response(self, text: str) -> str:
        cleaned = text.replace("\\circ", " deg").replace("\\text", "")
        cleaned = cleaned.replace("$", "").replace("\\", "")
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, (list, dict)):
                return json.dumps(parsed, ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            pass
        return cleaned.strip()
