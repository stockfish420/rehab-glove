const STATE_STYLES = {
  REST: "border-slate-500 bg-slate-800 text-slate-100",
  FLEXION: "border-emerald-400 bg-emerald-500/15 text-emerald-200",
  EXTENSION: "border-cyan-400 bg-cyan-500/15 text-cyan-200",
};

export default function StateIndicator({ state, repCount }) {
  const normalizedState = state || "REST";
  const stateClass = STATE_STYLES[normalizedState] ?? STATE_STYLES.REST;

  return (
    <section className="shrink-0 rounded-lg border border-cyan-900/60 bg-slate-900 p-4 shadow-lg shadow-slate-950/20">
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
            Current State
          </p>
          <span
            className={`mt-2 inline-flex rounded-full border px-4 py-1.5 text-sm font-bold ${stateClass}`}
          >
            {normalizedState}
          </span>
        </div>

        <div className="text-right">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
            Completed
          </p>
          <p className="mt-1 text-4xl font-black tracking-normal text-cyan-50">
            REP {repCount}
          </p>
        </div>
      </div>
    </section>
  );
}
