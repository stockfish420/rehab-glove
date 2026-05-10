import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from "recharts";

export default function AngleChart({ history }) {
  const data = history.map((point, index) => ({
    index: index + 1,
    optical: point.optical,
    sensor: point.sensor,
    pressure: point.pressure,
  }));

  return (
    <section className="flex min-h-0 flex-col rounded-lg border border-cyan-900/60 bg-slate-900 p-3 shadow-lg shadow-slate-950/20">
      <div className="mb-2 flex shrink-0 items-center justify-between">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-cyan-100">
          Sensor Fusion Tracking
        </h2>
        <span className="text-xs text-slate-500">Last 60 frames</span>
      </div>

      <div className="min-h-0 flex-1">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 8, bottom: 4, left: -12 }}>
            <CartesianGrid stroke="#164e63" strokeDasharray="3 3" />
            <XAxis
              dataKey="index"
              stroke="#94a3b8"
              tick={{ fill: "#94a3b8", fontSize: 11 }}
              tickLine={false}
            />
            <YAxis
              yAxisId="angle"
              domain={[0, 90]}
              stroke="#94a3b8"
              tick={{ fill: "#94a3b8", fontSize: 11 }}
              tickLine={false}
              unit="deg"
            />
            <YAxis
              yAxisId="pressure"
              orientation="right"
              domain={[0, 10]}
              stroke="#34d399"
              tick={{ fill: "#34d399", fontSize: 11 }}
              tickLine={false}
              unit="N"
            />
            <Legend wrapperStyle={{ color: "#cbd5e1", fontSize: 12 }} />
            <Line
              yAxisId="angle"
              type="monotone"
              dataKey="optical"
              name="Optical"
              stroke="#38bdf8"
              strokeWidth={2}
              dot={false}
              connectNulls
              isAnimationActive={false}
            />
            <Line
              yAxisId="angle"
              type="monotone"
              dataKey="sensor"
              name="Sensor"
              stroke="#f59e0b"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
            <Line
              yAxisId="pressure"
              type="monotone"
              dataKey="pressure"
              name="Pressure"
              stroke="#34d399"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
