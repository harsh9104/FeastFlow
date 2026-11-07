import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export interface Point {
  t: string;
  v: number | null;
}
export interface Series {
  unit: string;
  points: Point[];
}
export interface LineSpec {
  key: string;
  label: string;
  color: string;
  step?: boolean;
  scale?: number; // multiply raw values (e.g. 1000 to show seconds as ms)
}

// Mid-tone colours that stay readable on both the light and dark theme.
export const COLORS = { blue: "#3b82f6", orange: "#f97316", green: "#22c55e", red: "#ef4444", violet: "#8b5cf6" };

const hhmm = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

export default function MetricChart({
  title,
  series,
  lines,
  unit,
  domain,
}: {
  title: string;
  series: Record<string, Series>;
  lines: LineSpec[];
  unit?: string;
  domain?: [number | "auto", number | "auto"];
}) {
  const first = series[lines[0].key]?.points ?? [];
  const data = first.map((p, i) => {
    const row: Record<string, number | string | null> = { t: p.t };
    for (const l of lines) {
      const v = series[l.key]?.points[i]?.v ?? null;
      row[l.key] = v === null ? null : v * (l.scale ?? 1);
    }
    return row;
  });
  const empty = data.every((r) => lines.every((l) => r[l.key] === null));

  return (
    <div className="card chart">
      <h3>{title}</h3>
      {empty ? (
        <p className="muted pad">No data in this range yet.</p>
      ) : (
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#8884" />
            <XAxis dataKey="t" tickFormatter={hhmm} minTickGap={40} fontSize={12} stroke="#888" />
            <YAxis fontSize={12} stroke="#888" unit={unit} domain={domain ?? ["auto", "auto"]} allowDecimals={false} />
            <Tooltip
              labelFormatter={(v) => new Date(v as string).toLocaleString()}
              formatter={(v: number) => (typeof v === "number" ? v.toFixed(1) : v)}
              contentStyle={{ background: "var(--card)", border: "1px solid var(--border)", color: "var(--text)" }}
            />
            {lines.length > 1 && <Legend />}
            {lines.map((l) => (
              <Line
                key={l.key}
                name={l.label}
                dataKey={l.key}
                stroke={l.color}
                strokeWidth={2}
                dot={false}
                connectNulls={false}
                type={l.step ? "stepAfter" : "monotone"}
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
