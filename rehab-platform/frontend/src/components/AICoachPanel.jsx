import { useEffect, useState } from "react";

export default function AICoachPanel({ critique, isConnected, logs, progress, onSendMessage }) {
  const [activeTab, setActiveTab] = useState("chat");
  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      text: "Start a session, complete a rep, or ask about the live readings.",
    },
  ]);
  const [isPulsing, setIsPulsing] = useState(false);

  useEffect(() => {
    if (!critique) {
      return undefined;
    }

    setMessages((current) => [...current, { role: "assistant", text: critique }].slice(-20));
    setIsPulsing(true);
    const timer = window.setTimeout(() => setIsPulsing(false), 1000);

    return () => window.clearTimeout(timer);
  }, [critique]);

  async function handleSubmit(event) {
    event.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || isSending) {
      return;
    }

    setInput("");
    setIsSending(true);
    setMessages((current) => [...current, { role: "user", text: trimmed }].slice(-20));

    try {
      const response = await onSendMessage(trimmed);
      setMessages((current) => [...current, { role: "assistant", text: response }].slice(-20));
    } catch (error) {
      const message = error instanceof Error ? error.message : "LLM chat failed";
      setMessages((current) => [...current, { role: "assistant", text: message }].slice(-20));
    } finally {
      setIsSending(false);
    }
  }

  return (
    <aside
      className={`flex min-h-0 flex-col rounded-lg border border-cyan-900/60 bg-slate-900 shadow-xl shadow-slate-950/30 ${
        isPulsing ? "animate-pulse" : ""
      }`}
    >
      <div className="flex shrink-0 items-center gap-3 border-b border-cyan-900/50 p-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-cyan-400/10 text-xl">
          {"\u{1F9E0}"}
        </div>
        <div className="min-w-0">
          <h2 className="truncate text-sm font-bold text-cyan-50">AI Biomechanical Coach</h2>
          <p className={isConnected ? "text-xs text-emerald-300" : "text-xs text-rose-300"}>
            {isConnected ? "Live analysis ready" : "Waiting for backend"}
          </p>
        </div>
      </div>

      <div className="grid shrink-0 grid-cols-2 border-b border-cyan-900/50 p-2">
        <button
          type="button"
          onClick={() => setActiveTab("chat")}
          className={`rounded-md px-3 py-2 text-xs font-bold transition ${
            activeTab === "chat"
              ? "bg-cyan-400 text-slate-950"
              : "text-slate-400 hover:bg-slate-800 hover:text-slate-100"
          }`}
        >
          LLM Live Chat
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("logs")}
          className={`rounded-md px-3 py-2 text-xs font-bold transition ${
            activeTab === "logs"
              ? "bg-cyan-400 text-slate-950"
              : "text-slate-400 hover:bg-slate-800 hover:text-slate-100"
          }`}
        >
          LLM Feed Logs
        </button>
      </div>

      <div className="shrink-0 border-b border-cyan-900/50 px-3 py-2">
        <div className="mb-1 flex items-center justify-between gap-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
          <span>Report Generation</span>
          <span>
            {progress.percent ?? 0}%
          </span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-slate-950">
          <div
            className="h-full rounded-full bg-cyan-400 transition-all duration-500"
            style={{ width: `${progress.percent ?? 0}%` }}
          />
        </div>
        <div className="mt-1 flex items-center justify-between text-[11px] text-slate-500">
          <span>
            {progress.processing
              ? `Analyzing rep ${progress.processing.rep_number}`
              : progress.phase || "Idle"}
          </span>
          <span>{progress.queued ?? 0} queued</span>
        </div>
      </div>

      {activeTab === "chat" ? (
        <>
          <div className="min-h-0 flex-1 space-y-2 overflow-auto p-3">
            {messages.map((message, index) => (
              <div
                key={`${message.role}-${index}`}
                className={`rounded-md border px-3 py-2 text-sm leading-5 ${
                  message.role === "user"
                    ? "ml-6 border-cyan-800 bg-cyan-950/60 text-cyan-50"
                    : "mr-6 border-slate-700 bg-slate-950 text-slate-100"
                }`}
              >
                {message.text}
              </div>
            ))}
          </div>

          <form onSubmit={handleSubmit} className="flex shrink-0 gap-2 border-t border-cyan-900/50 p-3">
            <input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="Ask about form, pressure, or accuracy"
              className="min-w-0 flex-1 rounded-md border border-cyan-900/60 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none transition placeholder:text-slate-500 focus:border-cyan-400"
            />
            <button
              type="submit"
              disabled={isSending || !input.trim()}
              className="rounded-md bg-emerald-400 px-3 py-2 text-sm font-bold text-slate-950 transition hover:bg-emerald-300 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
            >
              {isSending ? "..." : "Send"}
            </button>
          </form>
        </>
      ) : (
        <div className="min-h-0 flex-1 space-y-2 overflow-auto p-3">
          {logs.length === 0 ? (
            <p className="rounded-md border border-slate-700 bg-slate-950 p-3 text-sm text-slate-400">
              No LLM payloads yet. Complete a rep to see the exact KPI data sent for analysis.
            </p>
          ) : (
            logs
              .slice()
              .reverse()
              .map((log, index) => (
                <article
                  key={`${log.rep_number}-${log.status}-${index}`}
                  className="rounded-md border border-cyan-900/50 bg-slate-950 p-3 text-xs text-slate-300"
                >
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <span className="font-bold text-cyan-100">Rep {log.rep_number}</span>
                    <span
                      className={
                        log.status === "complete"
                          ? "text-emerald-300"
                          : log.status === "processing"
                            ? "text-cyan-300"
                          : "text-amber-300"
                      }
                    >
                      {log.status}
                    </span>
                  </div>
                  <pre className="max-h-28 overflow-auto whitespace-pre-wrap rounded bg-slate-900 p-2">
                    {JSON.stringify(log.payload, null, 2)}
                  </pre>
                  {log.response && (
                    <p className="mt-2 border-t border-slate-800 pt-2 text-slate-100">
                      {log.response}
                    </p>
                  )}
                  {log.flag && log.flag !== "NO_FLAG" && (
                    <p className="mt-2 rounded border border-amber-500/40 bg-amber-500/10 p-2 text-amber-200">
                      {log.flag}
                    </p>
                  )}
                </article>
              ))
          )}
        </div>
      )}
    </aside>
  );
}
