import { useState } from "react";
import AICoachPanel from "./components/AICoachPanel.jsx";
import AngleChart from "./components/AngleChart.jsx";
import KPIGauge from "./components/KPIGauge.jsx";
import SessionModal from "./components/SessionModal.jsx";
import StateIndicator from "./components/StateIndicator.jsx";
import VideoPanel from "./components/VideoPanel.jsx";
import { useRehabSocket } from "./hooks/useRehabSocket.js";

export default function App() {
  const [sessionActive, setSessionActive] = useState(false);
  const {
    opticalAngle,
    sensorAngle,
    pressure,
    exerciseState,
    repCount,
    latestCritique,
    llmLogs,
    llmProgress,
    connectionStatus,
    angleHistory,
    startSession,
    stopSession,
    endSession,
    generateReport,
    sendChatMessage,
  } = useRehabSocket(sessionActive);

  const [showModal, setShowModal] = useState(false);
  const [sessionSummary, setSessionSummary] = useState(null);
  const [isGeneratingReport, setIsGeneratingReport] = useState(false);
  const [hasStoppedSession, setHasStoppedSession] = useState(false);

  const isConnected = connectionStatus === "connected";

  async function handleStartSession() {
    try {
      await startSession();
      setSessionActive(true);
      setHasStoppedSession(false);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to start session";
      setSessionSummary(message);
      setShowModal(true);
    }
  }

  async function handleStopSession() {
    setSessionActive(false);
    await stopSession();
    setHasStoppedSession(true);
  }

  async function handleEndSession() {
    setSessionActive(false);
    setHasStoppedSession(true);
    await endSession();
  }

  async function handleGenerateReport() {
    setIsGeneratingReport(true);

    try {
      const nextSummary = await generateReport();
      setSessionSummary(nextSummary);
      setHasStoppedSession(false);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to generate report";
      setSessionSummary(`Session report unavailable.\n\n${message}`);
    } finally {
      setShowModal(true);
      setIsGeneratingReport(false);
    }
  }

  return (
    <main className="h-screen overflow-hidden bg-slate-950 text-slate-100">
      <header className="h-16 border-b border-cyan-900/60 bg-slate-950">
        <div className="flex h-full items-center justify-between gap-4 px-4 lg:px-5">
          <div>
            <h1 className="text-lg font-black tracking-normal text-cyan-100">REHAB PLATFORM</h1>
            <p className="text-xs text-slate-400">Diagnostic hand rehabilitation command center</p>
          </div>

          <div className="flex flex-wrap items-center justify-end gap-3">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-300">
              <span
                className={`h-2.5 w-2.5 rounded-full ${
                  isConnected ? "bg-emerald-400 shadow-[0_0_12px_#34d399]" : "bg-rose-500"
                }`}
              />
              {connectionStatus}
            </div>

            <button
              type="button"
              onClick={sessionActive ? handleStopSession : handleStartSession}
              disabled={isGeneratingReport}
              className={`rounded-md px-3 py-2 text-sm font-bold transition ${
                sessionActive
                  ? "bg-rose-500 text-white hover:bg-rose-400"
                  : "bg-emerald-400 text-slate-950 hover:bg-emerald-300"
              } disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400`}
            >
              {sessionActive ? "Stop Session" : "Start Session"}
            </button>

            <button
              type="button"
              onClick={handleGenerateReport}
              disabled={sessionActive || !hasStoppedSession || isGeneratingReport}
              className="rounded-md bg-cyan-400 px-3 py-2 text-sm font-bold text-slate-950 transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
            >
              {isGeneratingReport ? "Generating..." : "Generate Report"}
            </button>
          </div>
        </div>
      </header>

      <div className="grid h-[calc(100vh-4rem)] min-h-0 gap-3 overflow-hidden p-3 lg:grid-cols-[minmax(0,1.55fr)_minmax(320px,0.72fr)]">
        <section className="flex min-h-0 flex-col gap-3">
          <StateIndicator state={exerciseState} repCount={repCount} />

          <div className="grid min-h-0 flex-1 gap-3 lg:grid-cols-[minmax(0,1.15fr)_minmax(300px,0.85fr)]">
            <VideoPanel isActive={sessionActive} />
            <AngleChart history={angleHistory} />
          </div>

          <div className="grid h-36 shrink-0 gap-3 md:grid-cols-3">
            <KPIGauge
              label="Optical Angle"
              value={opticalAngle}
              unit="deg"
              min={0}
              max={90}
              color="#38bdf8"
            />
            <KPIGauge
              label="Sensor Angle"
              value={sensorAngle}
              unit="deg"
              min={0}
              max={90}
              color="#f59e0b"
            />
            <KPIGauge
              label="Pressure"
              value={pressure}
              unit="N"
              min={0}
              max={10}
              color="#34d399"
            />
          </div>
        </section>

        <AICoachPanel
          critique={latestCritique}
          isConnected={isConnected}
          logs={llmLogs}
          progress={llmProgress}
          onSendMessage={sendChatMessage}
        />
      </div>

      <SessionModal
        isOpen={showModal}
        summary={sessionSummary}
        onClose={() => setShowModal(false)}
      />
    </main>
  );
}
