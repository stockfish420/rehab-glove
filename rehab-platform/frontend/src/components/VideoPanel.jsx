const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export default function VideoPanel({ isActive }) {
  return (
    <section className="flex min-h-0 flex-col overflow-hidden rounded-lg border border-cyan-900/60 bg-slate-900 shadow-lg shadow-slate-950/20">
      <div className="flex shrink-0 items-center justify-between border-b border-cyan-900/50 px-3 py-2">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-cyan-100">
          Live Computer Vision
        </h2>
        <span className={isActive ? "text-xs text-emerald-300" : "text-xs text-slate-500"}>
          {isActive ? "Streaming" : "Idle"}
        </span>
      </div>

      <div className="min-h-0 flex-1 bg-slate-950">
        {isActive ? (
          <img
            src={`${API_URL}/video`}
            alt="Live annotated hand tracking feed"
            className="h-full w-full object-cover"
          />
        ) : (
          <div className="flex h-full items-center justify-center text-sm font-semibold text-slate-500">
            Press Start Session
          </div>
        )}
      </div>
    </section>
  );
}
