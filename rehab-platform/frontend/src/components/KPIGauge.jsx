export default function KPIGauge({ label, value, unit, min, max, color }) {
  const hasValue = value !== null && Number.isFinite(value);
  const range = max - min;
  const percent = hasValue && range > 0 ? ((value - min) / range) * 100 : 0;
  const clampedPercent = Math.min(100, Math.max(0, percent));
  const displayValue = hasValue ? value.toFixed(1) : "---";

  return (
    <section className="h-full rounded-lg border border-cyan-900/60 bg-slate-900 p-3 shadow-lg shadow-slate-950/20">
      <div className="mb-2 flex items-start justify-between gap-2">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">{label}</p>
          <p className="mt-0.5 text-xl font-bold text-cyan-50">
            {displayValue}
            {hasValue && <span className="ml-1 text-xs font-medium text-slate-400">{unit}</span>}
          </p>
        </div>
      </div>

      <div className="flex h-[76px] items-end gap-2">
        <div className="relative h-full w-9 overflow-hidden rounded-md border border-cyan-900/60 bg-slate-950">
          <div
            className="absolute bottom-0 left-0 w-full rounded-t-md transition-all duration-300"
            style={{
              height: `${clampedPercent}%`,
              backgroundColor: color,
            }}
          />
        </div>

        <div className="flex h-full flex-col justify-between text-[10px] text-slate-500">
          <span>
            {max}
            {unit}
          </span>
          <span>
            {min}
            {unit}
          </span>
        </div>
      </div>
    </section>
  );
}
