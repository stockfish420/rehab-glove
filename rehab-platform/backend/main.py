"""FastAPI orchestration layer for the rehab platform."""

import asyncio
import os
import time
from contextlib import asynccontextmanager

import cv2
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from serial_reader import SerialReader
from vision_engine import VisionEngine
from state_machine import RepStateMachine
from llm_worker import LLM_TIMEOUT_SECONDS, LLMWorker
from models import RepKPI


FRAME_INTERVAL_SECONDS = 0.033
VIDEO_INTERVAL_SECONDS = 0.066


class ChatRequest(BaseModel):
    message: str


def get_llm_progress(app: FastAPI) -> dict[str, object]:
    return app.state.report_progress


def set_report_progress(
    app: FastAPI,
    percent: int,
    phase: str,
    is_generating: bool,
) -> None:
    app.state.report_progress = {
        "percent": max(0, min(100, percent)),
        "phase": phase,
        "is_generating": is_generating,
        "queued": len(app.state.llm_analysis_queue),
        "processing": app.state.llm_processing,
    }


def update_llm_log(app: FastAPI, log_id: int, patch: dict[str, object]) -> None:
    for index, log in enumerate(app.state.llm_logs):
        if log["id"] == log_id:
            app.state.llm_logs[index] = {**log, **patch}
            return


def remove_from_analysis_queue(app: FastAPI, log_id: int) -> None:
    app.state.llm_analysis_queue = [
        item for item in app.state.llm_analysis_queue if item["log_id"] != log_id
    ]


def analysis_queue_has(app: FastAPI, log_id: int) -> bool:
    return any(item["log_id"] == log_id for item in app.state.llm_analysis_queue)


async def enqueue_rep_analysis(app: FastAPI, kpi: RepKPI) -> None:
    log_id = app.state.llm_next_log_id
    app.state.llm_next_log_id += 1

    log_entry = {
        "id": log_id,
        "type": "rep_critique",
        "rep_number": kpi.rep_number,
        "payload": kpi.model_dump(),
        "status": "queued_live",
    }
    app.state.llm_logs.append(log_entry)
    app.state.llm_logs = app.state.llm_logs[-50:]
    app.state.llm_total += 1

    item = {"log_id": log_id, "kpi": kpi}

    if app.state.llm_processing is None and app.state.llm_service_item is None:
        app.state.llm_service_item = item
    else:
        if app.state.llm_service_item is not None:
            previous_live_item = app.state.llm_service_item
            if not analysis_queue_has(app, previous_live_item["log_id"]):
                app.state.llm_analysis_queue.append(previous_live_item)
            update_llm_log(
                app,
                previous_live_item["log_id"],
                {"status": "queued_final"},
            )
        app.state.llm_analysis_queue.append(item)
        app.state.llm_service_item = item

    app.state.llm_work_event.set()


async def llm_analysis_worker(app: FastAPI) -> None:
    while True:
        await app.state.llm_work_event.wait()

        if app.state.llm_service_item is not None:
            item = app.state.llm_service_item
            app.state.llm_service_item = None
            remove_from_analysis_queue(app, item["log_id"])
        elif app.state.llm_drain_final and app.state.llm_analysis_queue:
            item = app.state.llm_analysis_queue.pop(0)
        else:
            app.state.llm_work_event.clear()
            continue

        log_id = item["log_id"]
        kpi = item["kpi"]

        app.state.llm_processing = {
            "log_id": log_id,
            "rep_number": kpi.rep_number,
        }
        app.state.llm_analysis_started_at = time.time()
        update_llm_log(app, log_id, {"status": "processing"})

        try:
            elapsed_seconds = int(kpi.timestamp - app.state.session_started_at)
            critique = await app.state.llm_worker.get_rep_critique(kpi, elapsed_seconds)
            durations = [
                max(0.0, current.timestamp - previous.timestamp)
                for previous, current in zip(app.state.session_kpis, app.state.session_kpis[1:])
            ]
            rep_duration = durations[-1] if durations else 0.0
            mean_duration = sum(durations) / len(durations) if durations else rep_duration
            anomaly = await app.state.llm_worker.get_anomaly_flag(
                kpi,
                rep_duration=rep_duration,
                session_mean_duration=mean_duration,
            )
            if anomaly and anomaly.strip() != "NO_FLAG":
                app.state.session_flags.append(anomaly.strip())

            app.state.latest_critique = critique
            update_llm_log(
                app,
                log_id,
                {
                    "status": "complete",
                    "response": critique,
                    "flag": anomaly,
                },
            )
        except Exception as exc:
            update_llm_log(
                app,
                log_id,
                {
                    "status": "failed",
                    "response": f"Analysis failed: {exc}",
                },
            )
        finally:
            app.state.llm_completed += 1
            app.state.llm_processing = None
            app.state.llm_analysis_started_at = None

            if app.state.llm_service_item is not None or (
                app.state.llm_drain_final and app.state.llm_analysis_queue
            ):
                app.state.llm_work_event.set()
            else:
                app.state.llm_work_event.clear()


@asynccontextmanager
async def lifespan(app: FastAPI):
    serial_port = os.getenv("SERIAL_PORT", "/dev/ttyUSB0")
    serial_baud = int(os.getenv("SERIAL_BAUD", "115200"))
    camera_index = int(os.getenv("CAMERA_INDEX", "0"))

    app.state.serial_reader = SerialReader(port=serial_port, baud=serial_baud)
    app.state.vision_engine = VisionEngine(camera_index=camera_index)
    app.state.state_machine = RepStateMachine()
    app.state.llm_worker = LLMWorker()
    app.state.session_kpis: list[RepKPI] = []
    app.state.session_flags: list[str] = []
    app.state.llm_logs: list[dict[str, object]] = []
    app.state.llm_service_item = None
    app.state.llm_analysis_queue: list[dict[str, object]] = []
    app.state.llm_work_event = asyncio.Event()
    app.state.llm_drain_final = False
    app.state.llm_total = 0
    app.state.llm_completed = 0
    app.state.llm_processing = None
    app.state.llm_analysis_started_at = None
    app.state.llm_next_log_id = 1
    app.state.latest_critique = None
    app.state.session_started_at = time.time()
    app.state.report_progress = {
        "percent": 0,
        "phase": "Idle",
        "is_generating": False,
        "queued": 0,
        "processing": None,
    }

    app.state.serial_reader.start()
    app.state.vision_engine.start()
    app.state.llm_worker_task = asyncio.create_task(llm_analysis_worker(app))

    try:
        yield
    finally:
        app.state.llm_worker_task.cancel()
        try:
            await app.state.llm_worker_task
        except asyncio.CancelledError:
            pass
        app.state.serial_reader.stop()
        app.state.vision_engine.stop()


app = FastAPI(
    title="Diagnostic Hand Rehabilitation Platform",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, bool | str]:
    llm_available = await asyncio.to_thread(app.state.llm_worker.is_available)

    return {
        "status": "ok",
        "serial": app.state.serial_reader.is_connected,
        "vision": app.state.vision_engine.is_running,
        "llm": llm_available,
    }


@app.post("/session/end")
async def end_session() -> dict[str, str]:
    app.state.state_machine.reset()
    return {"status": "stopped"}


@app.get("/session/report/status")
async def report_status() -> dict[str, object]:
    return app.state.report_progress


@app.post("/session/report")
async def generate_report() -> dict[str, str]:
    set_report_progress(app, 5, "Preparing queued rep analysis", True)
    app.state.llm_drain_final = True
    app.state.llm_work_event.set()

    total_to_process = (
        len(app.state.llm_analysis_queue)
        + (1 if app.state.llm_service_item is not None else 0)
        + (1 if app.state.llm_processing is not None else 0)
    )

    while (
        app.state.llm_processing is not None
        or app.state.llm_service_item is not None
        or app.state.llm_analysis_queue
    ):
        remaining = (
            len(app.state.llm_analysis_queue)
            + (1 if app.state.llm_service_item is not None else 0)
            + (1 if app.state.llm_processing is not None else 0)
        )
        if total_to_process > 0:
            completed_ratio = (total_to_process - remaining) / total_to_process
            set_report_progress(
                app,
                5 + round(completed_ratio * 65),
                "Draining queued rep analyses",
                True,
            )
        await asyncio.sleep(0.2)

    set_report_progress(app, 75, "Generating clinical report", True)
    completed_kpis = list(app.state.session_kpis)
    summary = await app.state.llm_worker.get_session_summary(
        completed_kpis,
        flags=list(app.state.session_flags),
    )
    set_report_progress(app, 100, "Report complete", False)

    app.state.state_machine.reset()
    app.state.session_kpis.clear()
    app.state.session_flags.clear()

    return {"summary": summary}


@app.post("/session/start")
async def start_session() -> dict[str, str]:
    app.state.state_machine.reset()
    app.state.session_kpis.clear()
    app.state.session_flags.clear()
    app.state.llm_logs.clear()
    app.state.llm_service_item = None
    app.state.llm_analysis_queue.clear()
    app.state.llm_drain_final = False
    app.state.llm_work_event.clear()
    app.state.llm_total = 0
    app.state.llm_completed = 0
    app.state.llm_processing = None
    app.state.llm_analysis_started_at = None
    app.state.latest_critique = None
    app.state.session_started_at = time.time()
    set_report_progress(app, 0, "Idle", False)
    return {"status": "started"}


@app.post("/session/stop")
async def stop_session() -> dict[str, str]:
    return {"status": "stopped"}


@app.post("/llm/chat")
async def llm_chat(request: ChatRequest) -> dict[str, str]:
    sensor_reading = app.state.serial_reader.get_latest()
    context = {
        "state": app.state.state_machine.current_state,
        "rep_count": app.state.state_machine.rep_count,
        "optical_angle": app.state.vision_engine.get_angle(),
        "sensor_angle": sensor_reading.angle_sensor if sensor_reading else None,
        "pressure": sensor_reading.pressure if sensor_reading else None,
    }
    response = await app.state.llm_worker.get_live_chat_response(request.message, context)
    return {"response": response}


@app.get("/video")
async def video_feed() -> StreamingResponse:
    async def stream_frames():
        while True:
            frame = app.state.vision_engine.get_latest_frame()
            if frame is None:
                frame = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(
                    frame,
                    "Waiting for camera...",
                    (150, 240),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1.0,
                    (200, 200, 200),
                    2,
                    cv2.LINE_AA,
                )

            ok, encoded = cv2.imencode(
                ".jpg",
                frame,
                [int(cv2.IMWRITE_JPEG_QUALITY), 80],
            )
            if ok:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + encoded.tobytes()
                    + b"\r\n"
                )

            await asyncio.sleep(VIDEO_INTERVAL_SECONDS)

    return StreamingResponse(
        stream_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()

    try:
        while True:
            optical_angle = app.state.vision_engine.get_angle()
            sensor_reading = app.state.serial_reader.get_latest()

            sensor_angle = 0.0
            pressure = 0.0

            if sensor_reading is not None:
                sensor_angle = sensor_reading.angle_sensor
                pressure = sensor_reading.pressure
                completed_kpi = app.state.state_machine.update(
                    optical_angle,
                    sensor_reading.angle_sensor,
                    sensor_reading.pressure,
                )

                if completed_kpi is not None:
                    app.state.session_kpis.append(completed_kpi)
                    await enqueue_rep_analysis(app, completed_kpi)

            critique_for_frame = app.state.latest_critique
            app.state.latest_critique = None

            await websocket.send_json(
                {
                    "type": "frame",
                    "optical_angle": optical_angle,
                    "sensor_angle": sensor_angle,
                    "pressure": pressure,
                    "state": app.state.state_machine.current_state,
                    "rep_count": app.state.state_machine.rep_count,
                    "llm_critique": critique_for_frame,
                    "llm_logs": app.state.llm_logs[-30:],
                    "llm_progress": get_llm_progress(app),
                }
            )

            await asyncio.sleep(FRAME_INTERVAL_SECONDS)

    except WebSocketDisconnect:
        pass
