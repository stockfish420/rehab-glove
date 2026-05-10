# 4. Implementation

This section describes the practical implementation of the Diagnostic Hand Rehabilitation Platform. The system was implemented as an integrated edge-compute rehabilitation tool combining an Arduino Uno sensor node, a Python FastAPI backend, MediaPipe-based computer vision, a local Ollama large language model, and a React command-center dashboard. The design objective was to provide real-time repetition tracking, sensor-vision comparison, grip pressure monitoring, and clinical coaching feedback without relying on cloud processing.

## 4.1 Assembly

The hardware assembly was designed around a low-cost Arduino Uno acting as a dedicated sensor acquisition node. The Arduino was configured as a "dumb" sensor node, meaning that it performs only local analogue sampling, baseline calibration, simple signal normalization, and serial transmission. Higher-level interpretation, repetition detection, video processing, and clinical feedback generation are handled by the host computer.

The bend sensor was connected to analogue pin `A0` and positioned so that its resistance changed with finger flexion. A moisture/pressure sensor used as a grip-force proxy was connected to analogue pin `A1`. A PIR input was connected to digital pin `2`, allowing the firmware to include a simple binary movement or presence channel in the transmitted data stream. The Arduino communicates only through USB serial; no display, Bluetooth module, SD card, or additional embedded communication hardware was used.

At startup, the Arduino performs rest-state calibration by averaging 100 samples from both analogue channels. This baseline calibration is important because bend and pressure sensors vary significantly depending on placement, wiring, and resting mechanical stress. After calibration, the firmware samples at a fixed interval of 50 ms, corresponding to 20 Hz. Timing is implemented using `millis()` rather than `delay()`, which keeps the firmware loop non-blocking and allows stable periodic sampling.

Raw bend and pressure values are converted into percentage values using directional deltas from the calibrated rest baseline. Small deadbands are applied to suppress noise near the resting state. The bend channel uses a full-scale raw delta of 250 ADC counts, while the pressure channel uses a full-scale raw delta of 45 ADC counts, reflecting the higher sensitivity of the pressure sensor. Each transmitted line follows a comma-separated format:

```text
bend_percent,pressure_percent,pir
```

The serial baud rate is `115200`, which is sufficient for 20 Hz streaming while keeping latency low. The backend later converts bend percentage into a 0-90 degree sensor angle and pressure percentage into a 0-10 N pressure estimate. Sensitivity multipliers are exposed in software so that the system can be tuned during practical testing without reflashing the Arduino.

The camera assembly uses a standard webcam positioned to view the user's hand during rehabilitation movement. The camera feed is processed on the host machine using MediaPipe hand landmark detection. For the primary range-of-motion measurement, the middle finger was selected because it provides a stable central reference and is less affected by lateral hand rotation than outer fingers.

## 4.2 Software

The software system was implemented as a Python and React monorepo. The backend is written using FastAPI and runs local background workers for serial acquisition, computer vision, repetition-state detection, and LLM-based clinical feedback. The frontend is implemented using React 18, Vite, Tailwind CSS, and Recharts.

The backend serial acquisition layer is implemented in `serial_reader.py`. A `SerialReader` class opens the configured serial port, reads Arduino CSV lines in a daemon thread, parses malformed lines safely, and stores the latest valid reading using a thread lock. This prevents serial I/O from blocking the FastAPI event loop. The backend expects the Arduino's real firmware output format of `bend_percent,pressure_percent,pir` at `115200` baud. It maps bend percentage to a sensor angle in degrees and pressure percentage to Newtons. Environment variables such as `BEND_SENSITIVITY` and `PRESSURE_SENSITIVITY` allow calibration adjustments during experiments.

The computer vision layer is implemented in `vision_engine.py`. A `VisionEngine` class opens the webcam in a background thread and processes frames using MediaPipe. The system supports both the older MediaPipe Solutions API and the newer MediaPipe Tasks API, allowing it to run with the installed MediaPipe package. The hand landmarker model is loaded from `backend/assets/hand_landmarker.task`. The middle finger landmarks are used for optical angle estimation, specifically landmarks 9, 10, and 11, corresponding to MCP, PIP, and DIP. The PIP joint angle is calculated using two 3D vectors and the dot-product arccosine method. The resulting optical angle is drawn onto the live frame, together with the detected hand landmarks.

The repetition logic is implemented in `state_machine.py`. The system uses a three-state model consisting of `REST`, `FLEXION`, and `EXTENSION`. A repetition is counted when the motion sequence follows `REST -> FLEXION -> EXTENSION -> REST`. The rest threshold is set at 15 degrees and the flexion threshold at 40 degrees. To reduce false positives from jitter, transition into flexion requires the optical angle to exceed the flexion threshold for three consecutive frames. During flexion, the system records the peak optical angle, peak sensor angle, and average pressure. When a rep completes, these values are packaged into a `RepKPI` model containing rep number, sensor angle, optical angle, accuracy delta, pressure, and timestamp.

The FastAPI application in `main.py` orchestrates the full system. On startup, it creates the serial reader, vision engine, repetition state machine, and local LLM worker. The `/ws` WebSocket endpoint streams live dashboard frames to the React frontend at approximately 30 fps. Each frame contains the current optical angle, sensor angle, pressure, state, repetition count, LLM logs, and report progress metadata. The `/video` endpoint streams annotated camera frames as MJPEG so the dashboard can show a live computer-vision panel.

Session control is separated into explicit operations. `/session/start` resets session data and starts a new capture period. `/session/end` stops the active session without generating a report. `/session/report` is a dedicated report-generation endpoint that drains queued LLM analysis work and then generates the final clinical report. `/session/report/status` allows the frontend to poll report progress while the report is being generated.

The LLM layer is implemented in `llm_worker.py` and uses a local Ollama server at `http://localhost:11434` with the `gemma4:e2b` model. Ollama calls are synchronous at the library level, so the backend wraps them in `asyncio.to_thread()` to avoid blocking the FastAPI event loop. The LLM prompts are structured around ARIA, a clinical hand rehabilitation assistant. The system uses short per-rep coaching prompts, anomaly detection prompts, and formal post-session report prompts. Per-rep prompts are designed to generate concise one-sentence coaching feedback. Session report prompts generate a summary, observations, flags, trend indicators, and recommendations.

To prevent local LLM overload, the backend uses a two-lane queue strategy. If the LLM is free, the most recent completed rep is sent immediately for live coaching. If the LLM is already processing, newer reps are prioritized for live service while older reps are retained in a final-analysis queue. This ensures that real-time coaching remains relevant during fast sessions, while older rep data is still available for the final report. When the user clicks `Generate Report`, the queued data is processed sequentially and pooled into the report. The frontend displays report-generation progress rather than treating every live rep analysis as a user-facing progress event.

The frontend dashboard is implemented as a single-screen command center. It includes a session state display, live computer-vision feed, sensor fusion chart, KPI gauges, and an AI sidebar. The chart plots optical angle, sensor angle, and pressure simultaneously, with pressure mapped to a separate right-side axis. The AI sidebar contains two tabs: `LLM Live Chat`, for user questions during the session, and `LLM Feed Logs`, which displays rep payloads and LLM analysis status. A dedicated `Generate Report` button becomes available after the session is stopped.

## 4.3 Testing

Testing was performed at three levels: module verification, synthetic integration testing, and live hardware testing.

Module-level verification was performed using Python compilation checks and frontend production builds. Backend files were repeatedly checked using `py_compile` to ensure syntax correctness after changes to serial acquisition, vision processing, LLM queueing, and FastAPI orchestration. The frontend was verified with `npm run build`, which confirmed that the React components, hooks, Tailwind styling, and Recharts visualization compiled successfully.

A synthetic backend integration script was created in `backend/test_integration.py`. This script simulates the complete rehabilitation pipeline without physical hardware. The mock serial reader generates a sinusoidal sensor angle ranging from 0 to 80 degrees with a period of 3 seconds and constant pressure. The mock vision engine returns the same sinusoidal angle with Gaussian noise added. The state machine is then run at 20 Hz for 30 seconds. This test verifies that the repetition logic detects approximately 10 repetitions and asserts that at least 8 repetitions are detected. It also checks that the average sensor-vision accuracy delta remains below 10 degrees under simulated noise conditions.

Live hardware testing was performed with the Arduino Uno connected over USB serial and the webcam active. The Arduino firmware was uploaded and the serial monitor was closed before launching the backend to avoid port conflicts. The backend was started using the PowerShell launcher script `start.ps1`, which configures the serial port, starts Ollama if available, starts the FastAPI backend, starts the Vite frontend, and opens the dashboard. The launcher supports tuning parameters such as bend sensitivity and pressure sensitivity:

```powershell
.\start.ps1 -SerialPort COM3 -BendSensitivity 2.4 -PressureSensitivity 1.6
```

During live testing, the bend sensor initially under-reported movement compared with the visual angle. This was corrected by introducing a bend sensitivity multiplier in the backend. The pressure sensor was also made more responsive using a pressure sensitivity multiplier. These software-side calibration parameters allowed practical adjustment without modifying the Arduino firmware.

The computer-vision subsystem was tested by observing whether the annotated hand landmarks appeared on the dashboard video feed and whether the optical angle changed during finger flexion. The system was also adjusted to support the MediaPipe Tasks API after discovering that the installed MediaPipe package did not expose the older `mp.solutions` interface. The hand landmarker model was therefore loaded from a local `.task` file.

The LLM subsystem was tested by confirming that Ollama was reachable and that the `gemma4:e2b` model could respond from the backend virtual environment. Early testing showed that report generation could time out if many repetitions triggered overlapping LLM calls. This led to the implementation of the two-lane LLM queue strategy and the separation of session stopping from report generation. After this change, stopping a session preserves all collected data, and report generation is triggered explicitly using the `Generate Report` button.

End-to-end validation was performed through the dashboard. A typical test sequence consisted of starting a session, performing repeated hand flexion movements, observing rep count changes, checking the sensor fusion chart, reviewing live LLM coaching, stopping the session, and generating the report. Successful operation was confirmed when the dashboard displayed live video, detected repetitions, showed sensor and pressure trends, queued LLM analysis correctly, and generated a structured clinical report after the session was stopped.
