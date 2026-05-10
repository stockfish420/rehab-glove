import { useCallback, useEffect, useRef, useState } from "react";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const WS_URL = import.meta.env.VITE_WS_URL ?? "ws://localhost:8000/ws";
const MAX_RETRIES = 5;
const RETRY_DELAY_MS = 2000;
const HISTORY_LIMIT = 60;

export function useRehabSocket(enabled = false) {
  const socketRef = useRef(null);
  const retryCountRef = useRef(0);
  const reconnectTimerRef = useRef(null);
  const shouldReconnectRef = useRef(false);

  const [opticalAngle, setOpticalAngle] = useState(null);
  const [sensorAngle, setSensorAngle] = useState(0);
  const [pressure, setPressure] = useState(0);
  const [exerciseState, setExerciseState] = useState("REST");
  const [repCount, setRepCount] = useState(0);
  const [latestCritique, setLatestCritique] = useState(null);
  const [llmLogs, setLlmLogs] = useState([]);
  const [llmProgress, setLlmProgress] = useState({
    percent: 0,
    phase: "Idle",
    is_generating: false,
    queued: 0,
    processing: null,
  });
  const [connectionStatus, setConnectionStatus] = useState("disconnected");
  const [angleHistory, setAngleHistory] = useState([]);

  useEffect(() => {
    function closeSocket() {
      if (reconnectTimerRef.current !== null) {
        window.clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }

      if (socketRef.current !== null) {
        socketRef.current.close();
        socketRef.current = null;
      }
    }

    function connect() {
      setConnectionStatus("connecting");

      const socket = new WebSocket(WS_URL);
      socketRef.current = socket;

      socket.onopen = () => {
        retryCountRef.current = 0;
        setConnectionStatus("connected");
      };

      socket.onmessage = (event) => {
        let message;

        try {
          message = JSON.parse(event.data);
        } catch {
          return;
        }

        if (message.type !== "frame") {
          return;
        }

        const nextOpticalAngle = message.optical_angle ?? null;
        const nextSensorAngle = Number(message.sensor_angle ?? 0);
        const nextPressure = Number(message.pressure ?? 0);

        setOpticalAngle(nextOpticalAngle);
        setSensorAngle(nextSensorAngle);
        setPressure(nextPressure);
        setExerciseState(message.state ?? "REST");
        setRepCount(Number(message.rep_count ?? 0));

        if (message.llm_critique) {
          setLatestCritique(message.llm_critique);
        }

        if (message.llm_logs) {
          setLlmLogs(message.llm_logs);
        }

        if (message.llm_progress) {
          setLlmProgress(message.llm_progress);
        }

        setAngleHistory((currentHistory) => {
          const nextHistory = [
            ...currentHistory,
            {
              time: Date.now(),
              optical: nextOpticalAngle,
              sensor: nextSensorAngle,
              pressure: nextPressure,
            },
          ];

          return nextHistory.slice(-HISTORY_LIMIT);
        });
      };

      socket.onclose = () => {
        if (socketRef.current === socket) {
          socketRef.current = null;
        }

        setConnectionStatus("disconnected");

        if (!shouldReconnectRef.current || retryCountRef.current >= MAX_RETRIES) {
          return;
        }

        retryCountRef.current += 1;
        reconnectTimerRef.current = window.setTimeout(connect, RETRY_DELAY_MS);
      };

      socket.onerror = () => {
        socket.close();
      };
    }

    if (!enabled) {
      shouldReconnectRef.current = false;
      closeSocket();
      setConnectionStatus("disconnected");
      return undefined;
    }

    shouldReconnectRef.current = true;
    connect();

    return () => {
      shouldReconnectRef.current = false;
      closeSocket();
    };
  }, [enabled]);

  const startSession = useCallback(async () => {
    const response = await fetch(`${API_URL}/session/start`, {
      method: "POST",
    });

    if (!response.ok) {
      throw new Error("Failed to start session");
    }

    setOpticalAngle(null);
    setSensorAngle(0);
    setPressure(0);
    setExerciseState("REST");
    setRepCount(0);
    setLatestCritique(null);
    setLlmLogs([]);
    setLlmProgress({
      percent: 0,
      phase: "Idle",
      is_generating: false,
      queued: 0,
      processing: null,
    });
    setAngleHistory([]);
  }, []);

  const stopSession = useCallback(async () => {
    await fetch(`${API_URL}/session/stop`, {
      method: "POST",
    });
  }, []);

  const endSession = useCallback(async () => {
    const response = await fetch(`${API_URL}/session/end`, {
      method: "POST",
    });

    if (!response.ok) {
      throw new Error("Failed to end session");
    }
  }, []);

  const fetchReportStatus = useCallback(async () => {
    const response = await fetch(`${API_URL}/session/report/status`);
    if (!response.ok) {
      return;
    }

    const data = await response.json();
    setLlmProgress(data);
  }, []);

  const generateReport = useCallback(async () => {
    setLlmProgress({
      percent: 1,
      phase: "Starting report generation",
      is_generating: true,
      queued: 0,
      processing: null,
    });

    const statusTimer = window.setInterval(fetchReportStatus, 500);

    try {
      const response = await fetch(`${API_URL}/session/report`, {
        method: "POST",
      });

      if (!response.ok) {
        throw new Error("Failed to generate report");
      }

      const data = await response.json();
      await fetchReportStatus();
      return data.summary ?? "";
    } finally {
      window.clearInterval(statusTimer);
    }
  }, [fetchReportStatus]);

  const sendChatMessage = useCallback(async (message) => {
    const response = await fetch(`${API_URL}/llm/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ message }),
    });

    if (!response.ok) {
      throw new Error("Failed to send chat message");
    }

    const data = await response.json();
    return data.response ?? "";
  }, []);

  return {
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
  };
}
