import { useEffect, useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const DAYS = Array.from({ length: 31 }, (_, i) => {
  const day = String(i + 1).padStart(2, "0");
  return `2026-01-${day}`;
});

const PRICE_MIN = 50;
const PRICE_MAX = 300;

function isMissing(value) {
  return value === null || value === undefined || Number.isNaN(value);
}

function fmtMW(value) {
  if (isMissing(value)) return "—";
  return `${Math.round(value).toLocaleString("en-GB")} MW`;
}

function fmtPct(value) {
  if (isMissing(value)) return "—";
  return `${value.toFixed(1)}%`;
}

function fmtSkill(value) {
  if (isMissing(value)) return "—";
  const sign = value >= 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}`;
}

function fmtGBP(value) {
  if (isMissing(value)) return "—";
  return `£${value.toLocaleString("en-GB", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
}

function fmtTime(iso) {
  if (!iso) return "—";
  const dt = new Date(iso);
  return dt.toLocaleString("en-GB", {
    timeZone: "Europe/London",
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function fmtTick(iso) {
  const dt = new Date(iso);
  return dt.toLocaleString("en-GB", {
    timeZone: "Europe/London",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function clampPrice(value) {
  return Math.min(PRICE_MAX, Math.max(PRICE_MIN, value));
}

export default function App() {
  const [day, setDay] = useState("2026-01-15");
  const [summary, setSummary] = useState(null);
  const [detail, setDetail] = useState(null);
  const [meta, setMeta] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [darkMode, setDarkMode] = useState(true);
  const [tableSort, setTableSort] = useState({ column: 'mae', direction: 'asc' });
  const [alertThresholds, setAlertThresholds] = useState({ mae: 5000, bias: 3000 });

  // pricePerMwh is the committed value used for fetching;
  // priceInput is what the user is typing (debounced into pricePerMwh).
  const [pricePerMwh, setPricePerMwh] = useState(100);
  const [priceInput, setPriceInput] = useState("100");

  // Debounce the price input so we don't refetch on every keystroke.
  useEffect(() => {
    const parsed = Number(priceInput);
    if (priceInput.trim() === "" || Number.isNaN(parsed)) return undefined;
    const timer = setTimeout(() => {
      setPricePerMwh(clampPrice(parsed));
    }, 400);
    return () => clearTimeout(timer);
  }, [priceInput]);

  // Apply dark mode class to body
  useEffect(() => {
    if (darkMode) {
      document.body.classList.add('dark-mode');
      document.body.classList.remove('light-mode');
    } else {
      document.body.classList.add('light-mode');
      document.body.classList.remove('dark-mode');
    }
  }, [darkMode]);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [summaryRes, dayRes, metaRes] = await Promise.all([
          fetch("/api/summary"),
          fetch(`/api/day/${day}?price_per_mwh=${pricePerMwh}`),
          fetch("/api/meta"),
        ]);
        if (!summaryRes.ok || !dayRes.ok || !metaRes.ok) {
          throw new Error("The evaluation API returned an error.");
        }
        const [summaryJson, dayJson, metaJson] = await Promise.all([
          summaryRes.json(),
          dayRes.json(),
          metaRes.json(),
        ]);
        if (!cancelled) {
          setSummary(summaryJson);
          setDetail(dayJson);
          setMeta(metaJson);
        }
      } catch (err) {
        console.error("Error loading data:", err);
        if (!cancelled) setError(err.message || "Could not load data.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [day, pricePerMwh]);

  // Declared up front (before any memo that uses them) to avoid
  // "Cannot access ... before initialization" errors.
  const overall = useMemo(() => summary?.overall || {}, [summary]);
  const dayMetrics = useMemo(() => detail?.metrics || {}, [detail]);

  const chartData = useMemo(
    () =>
      (detail?.series || []).map((row) => ({
        ...row,
        label: fmtTick(row.t),
        band_range:
          !isMissing(row.band_high) && !isMissing(row.band_low)
            ? row.band_high - row.band_low
            : null,
      })),
    [detail],
  );

  const hourData = useMemo(
    () =>
      (summary?.by_hour || []).map((row) => ({
        hour: `${String(row.group).padStart(2, "0")}:00`,
        mae: row.mae,
      })),
    [summary],
  );

  const horizonData = useMemo(
    () =>
      (summary?.by_horizon || []).map((row) => ({
        bucket: row.group,
        mae: row.mae,
      })),
    [summary],
  );

  const errorDistribution = useMemo(() => {
    if (!detail?.series) return [];
    const errors = detail.series
      .filter((s) => !isMissing(s.error))
      .map((s) => s.error);
    if (errors.length === 0) return [];

    const min = Math.min(...errors);
    const max = Math.max(...errors);

    // All errors identical (or a single point): avoid dividing by zero.
    if (max === min) {
      return [{ range: `${Math.round(min)}`, count: errors.length }];
    }

    const binCount = 10;
    const binSize = (max - min) / binCount;

    const bins = Array.from({ length: binCount }, (_, i) => ({
      range: `${Math.round(min + i * binSize)} to ${Math.round(min + (i + 1) * binSize)}`,
      count: 0,
    }));

    errors.forEach((err) => {
      const binIndex = Math.min(Math.floor((err - min) / binSize), binCount - 1);
      bins[binIndex].count++;
    });

    return bins;
  }, [detail]);

  const cumulativeError = useMemo(() => {
    if (!detail?.series) return [];
    let cumulative = 0;
    return detail.series.map((s) => {
      if (!isMissing(s.error)) {
        cumulative += s.error;
      }
      return {
        label: fmtTick(s.t),
        cumulative,
      };
    });
  }, [detail]);


  const dayComparison = useMemo(() => {
    if (isMissing(dayMetrics.mae) || isMissing(overall.mae)) return null;
    const maeDiff = dayMetrics.mae - overall.mae;
    const maePctDiff = overall.mae > 0 ? (maeDiff / overall.mae) * 100 : 0;
    const biasDiff = (dayMetrics.bias ?? 0) - (overall.bias ?? 0);

    return {
      maeDiff,
      maePctDiff,
      biasDiff,
      isBetter: maeDiff < 0,
    };
  }, [dayMetrics, overall]);

  // Sorted daily data for table
  const sortedDaily = useMemo(() => {
    const daily = (summary?.daily || []).filter((r) => !isMissing(r.metrics?.mae));
    const sorted = [...daily].sort((a, b) => {
      let aVal, bVal;
      if (tableSort.column === 'delivery_day') {
        aVal = a.delivery_day;
        bVal = b.delivery_day;
      } else {
        aVal = a.metrics[tableSort.column] ?? 0;
        bVal = b.metrics[tableSort.column] ?? 0;
      }
      if (typeof aVal === 'string') {
        return tableSort.direction === 'asc' ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
      }
      return tableSort.direction === 'asc' ? aVal - bVal : bVal - aVal;
    });
    const bestDay = sorted[0]?.delivery_day;
    const worstDay = sorted[sorted.length - 1]?.delivery_day;
    return sorted.map((row) => ({
      ...row,
      isBest: row.delivery_day === bestDay,
      isWorst: row.delivery_day === worstDay,
    }));
  }, [summary, tableSort]);

  // Heatmap data: MAE by hour across all days
  const heatmapData = useMemo(() => {
    if (!summary?.daily) return [];
    const hours = Array.from({ length: 24 }, (_, i) => i);
    const days = (summary.daily || []).map(d => d.delivery_day);
    
    // Since we don't have hourly breakdown in daily data, create a placeholder
    // In a real implementation, you'd fetch hourly data for each day
    return hours.map(hour => ({
      hour: `${String(hour).padStart(2, '0')}:00`,
      ...days.reduce((acc, day) => {
        const dayData = summary.daily.find(d => d.delivery_day === day);
        acc[day] = dayData?.metrics?.mae || 0;
        return acc;
      }, {})
    }));
  }, [summary]);

  const handleSort = (column) => {
    setTableSort(prev => ({
      column,
      direction: prev.column === column && prev.direction === 'asc' ? 'desc' : 'asc'
    }));
  };

  const handleExport = () => {
    if (!detail?.series) return;
    const headers = ["Time (UTC ISO)", "Actual (MW)", "Forecast (MW)", "Error (MW)", "Publish Time (UTC ISO)"];
    const rows = detail.series.map((s) => [s.t, s.actual, s.forecast, s.error, s.publish]);
    const escape = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
    const csv = [headers, ...rows]
      .map((r) => r.map(escape).join(","))
      .join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `wind-forecast-${day}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (loading && !detail) {
    return (
      <div className="app">
        <div className="skeleton-grid">
          <div className="skeleton-header"></div>
          <div className="skeleton-kpis"></div>
          <div className="skeleton-panel"></div>
          <div className="skeleton-charts"></div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="app">
        <div className="card status error">{error}</div>
      </div>
    );
  }

  return (
    <div className="app">
      <header className="header">
        <div>
          <h1>Day-ahead GB wind, as of gate closure</h1>
          <p>
            Latest Elexon wind forecast available at 09:20 London on the day
            before delivery, compared with half-hourly outturn. January 2026 only.
          </p>
        </div>
        <div className="header-controls">
          <button className="btn-theme" onClick={() => setDarkMode(!darkMode)}>
            {darkMode ? "☀️ Light" : "🌙 Dark"}
          </button>
          <label className="day-picker">
            Delivery day
            <select value={day} onChange={(e) => setDay(e.target.value)}>
              {DAYS.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </label>
          <button className="btn-export" onClick={handleExport} disabled={!detail}>
            Export CSV
          </button>
          {loading && <span className="caption">Updating…</span>}
        </div>
      </header>

      <section className="kpis">
        <Kpi label="Decision cutoff" value={fmtTime(detail?.cutoff)} hint="D-1 09:20 London" />
        <Kpi label="Forecast used" value={fmtTime(detail?.latest_publish)} hint="Latest publish ≤ cutoff" />
        <Kpi 
          label="Day MAE" 
          value={fmtMW(dayMetrics.mae)} 
          hint="Mean absolute error"
          alert={dayMetrics.mae > alertThresholds.mae}
        />
        <Kpi 
          label="Day bias" 
          value={fmtMW(dayMetrics.bias)} 
          hint="Positive = over-forecast"
          alert={Math.abs(dayMetrics.bias) > alertThresholds.bias}
        />
        <Kpi label="January MAE" value={fmtMW(overall.mae)} hint="Full-month skill" />
        <Kpi label="January nMAE" value={fmtPct(overall.nmae_pct)} hint="% of mean actual" />
        <Kpi
          label="90% error range"
          value={`${fmtMW(overall.p5)} to ${fmtMW(overall.p95)}`}
          hint="5th–95th percentile of forecast − actual"
        />
        <Kpi
          label="Skill score"
          value={fmtSkill(detail?.skill_score?.skill_score)}
          hint="Positive = better than naive persistence forecast"
        />
        <Kpi
          label="Est. cost impact"
          value={fmtGBP(detail?.business_impact?.total_cost)}
          hint={`At £${pricePerMwh}/MWh`}
        />
        <Kpi
          label="Under-buy cost"
          value={fmtGBP(detail?.business_impact?.under_buy_cost)}
          hint="Over-forecast: expected more wind than arrived"
        />
      </section>

      <section className="card panel">
        <h2>Day vs month comparison</h2>
        <p className="caption">How this day's accuracy compares to January average.</p>
        {dayComparison && (
          <div className="comparison-grid">
            <div className="comparison-item">
              <span className="comparison-label">MAE difference</span>
              <span className={`comparison-value ${dayComparison.isBetter ? "positive" : "negative"}`}>
                {dayComparison.isBetter ? "↓" : "↑"} {fmtMW(Math.abs(dayComparison.maeDiff))}
              </span>
            </div>
            <div className="comparison-item">
              <span className="comparison-label">vs month average</span>
              <span className={`comparison-value ${dayComparison.isBetter ? "positive" : "negative"}`}>
                {dayComparison.maePctDiff > 0 ? "+" : ""}
                {dayComparison.maePctDiff.toFixed(1)}%
              </span>
            </div>
            <div className="comparison-item">
              <span className="comparison-label">Bias difference</span>
              <span className="comparison-value">{fmtMW(dayComparison.biasDiff)}</span>
            </div>
          </div>
        )}
      </section>

      <section className="card panel">
        <h2>Business impact scenario</h2>
        <p className="caption">Adjust wholesale price to see cost impact of forecast errors.</p>
        <div className="price-control">
          <label>
            Wholesale power price: £
            <input
              type="number"
              value={priceInput}
              onChange={(e) => setPriceInput(e.target.value)}
              onBlur={() => setPriceInput(String(pricePerMwh))}
              min={PRICE_MIN}
              max={PRICE_MAX}
              step="10"
            />
            /MWh
          </label>
          <div className="price-presets">
            {[50, 100, 150, 200].map((p) => (
              <button
                key={p}
                onClick={() => {
                  setPriceInput(String(p));
                  setPricePerMwh(p);
                }}
              >
                £{p}
              </button>
            ))}
          </div>
        </div>
        {detail?.business_impact && (
          <div className="impact-breakdown">
            <div className="impact-item">
              <span className="impact-label">Total cost impact</span>
              <span className="impact-value">{fmtGBP(detail.business_impact.total_cost)}</span>
            </div>
            <div className="impact-item">
              <span className="impact-label">Under-buy cost (over-forecast)</span>
              <span className="impact-value negative">{fmtGBP(detail.business_impact.under_buy_cost)}</span>
            </div>
            <div className="impact-item">
              <span className="impact-label">Over-buy cost (under-forecast)</span>
              <span className="impact-value">{fmtGBP(detail.business_impact.over_buy_cost)}</span>
            </div>
            <div className="impact-item">
              <span className="impact-label">Worst single period</span>
              <span className="impact-value">{fmtGBP(detail.business_impact.max_single_period_cost)}</span>
            </div>
          </div>
        )}
      </section>

      <section className="card panel">
        <h2>Alert thresholds</h2>
        <p className="caption">Set thresholds to highlight when metrics exceed limits.</p>
        <div className="threshold-control">
          <label>
            MAE alert threshold (MW):
            <input
              type="number"
              value={alertThresholds.mae}
              onChange={(e) => setAlertThresholds(prev => ({ ...prev, mae: Number(e.target.value) }))}
              min="0"
              step="500"
            />
          </label>
          <label>
            Bias alert threshold (MW):
            <input
              type="number"
              value={alertThresholds.bias}
              onChange={(e) => setAlertThresholds(prev => ({ ...prev, bias: Number(e.target.value) }))}
              min="0"
              step="500"
            />
          </label>
        </div>
      </section>

      <section className="card panel">
        <h2>Forecast vs actual</h2>
        <p className="caption">
          Shaded band is the 90% historical actual range given the forecast,
          using January-wide error percentiles.
        </p>
        <div className="legend">
          <span className="forecast">Forecast</span>
          <span className="actual">Actual</span>
          <span className="band">90% historical band</span>
        </div>
        <div style={{ width: "100%", height: 340 }}>
          <ResponsiveContainer>
            <ComposedChart data={chartData} margin={{ top: 8, right: 8, left: 8, bottom: 8 }}>
              <CartesianGrid stroke="#2a3a4d" strokeDasharray="3 3" />
              <XAxis dataKey="label" tick={{ fill: "#93a4b8", fontSize: 11 }} interval={3} />
              <YAxis
                tick={{ fill: "#93a4b8", fontSize: 11 }}
                tickFormatter={(v) => `${Math.round(v / 1000)}k`}
              />
              <Tooltip
                contentStyle={{ background: "#18222e", border: "1px solid #2a3a4d" }}
                formatter={(value, name) => [fmtMW(value), name]}
              />
              <Area
                type="monotone"
                dataKey="band_low"
                stackId="band"
                stroke="none"
                fill="transparent"
                name="Band floor"
                legendType="none"
              />
              <Area
                type="monotone"
                dataKey="band_range"
                stackId="band"
                stroke="none"
                fill="rgba(74, 163, 216, 0.22)"
                name="90% band"
                legendType="none"
              />
              <Line type="monotone" dataKey="forecast" stroke="#4aa3d8" dot={false} strokeWidth={2} name="Forecast" />
              <Line type="monotone" dataKey="actual" stroke="#d4a017" dot={false} strokeWidth={2} name="Actual" />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </section>

      <section className="charts-row">
        <div className="card panel">
          <h2>MAE by London hour</h2>
          <p className="caption">January average absolute error by delivery hour.</p>
          <div style={{ width: "100%", height: 220 }}>
            <ResponsiveContainer>
              <BarChart data={hourData}>
                <CartesianGrid stroke="#2a3a4d" strokeDasharray="3 3" />
                <XAxis dataKey="hour" tick={{ fill: "#93a4b8", fontSize: 10 }} interval={2} />
                <YAxis tick={{ fill: "#93a4b8", fontSize: 11 }} />
                <Tooltip
                  contentStyle={{ background: "#18222e", border: "1px solid #2a3a4d" }}
                  formatter={(value) => fmtMW(value)}
                />
                <Bar dataKey="mae" fill="#4aa3d8" name="MAE" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="card panel">
          <h2>MAE by forecast horizon</h2>
          <p className="caption">Horizon is startTime minus the publish used at cutoff.</p>
          <div style={{ width: "100%", height: 220 }}>
            <ResponsiveContainer>
              <BarChart data={horizonData}>
                <CartesianGrid stroke="#2a3a4d" strokeDasharray="3 3" />
                <XAxis dataKey="bucket" tick={{ fill: "#93a4b8", fontSize: 11 }} />
                <YAxis tick={{ fill: "#93a4b8", fontSize: 11 }} />
                <Tooltip
                  contentStyle={{ background: "#18222e", border: "1px solid #2a3a4d" }}
                  formatter={(value) => fmtMW(value)}
                />
                <Legend />
                <Bar dataKey="mae" fill="#6aae8a" name="MAE" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </section>

      <section className="charts-row">
        <div className="card panel">
          <h2>Error distribution</h2>
          <p className="caption">Histogram of forecast errors for selected day.</p>
          <div style={{ width: "100%", height: 220 }}>
            <ResponsiveContainer>
              <BarChart data={errorDistribution}>
                <CartesianGrid stroke="#2a3a4d" strokeDasharray="3 3" />
                <XAxis
                  dataKey="range"
                  tick={{ fill: "#93a4b8", fontSize: 9 }}
                  interval={0}
                  angle={-45}
                  textAnchor="end"
                  height={60}
                />
                <YAxis tick={{ fill: "#93a4b8", fontSize: 11 }} allowDecimals={false} />
                <Tooltip contentStyle={{ background: "#18222e", border: "1px solid #2a3a4d" }} />
                <Bar dataKey="count" fill="#c97848" name="Count" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="card panel">
          <h2>Cumulative error</h2>
          <p className="caption">Running sum of errors (shows bias accumulation).</p>
          <div style={{ width: "100%", height: 220 }}>
            <ResponsiveContainer>
              <AreaChart data={cumulativeError}>
                <CartesianGrid stroke="#2a3a4d" strokeDasharray="3 3" />
                <XAxis dataKey="label" tick={{ fill: "#93a4b8", fontSize: 10 }} interval={5} />
                <YAxis
                  tick={{ fill: "#93a4b8", fontSize: 11 }}
                  tickFormatter={(v) => `${Math.round(v / 1000)}k`}
                />
                <Tooltip
                  contentStyle={{ background: "#18222e", border: "1px solid #2a3a4d" }}
                  formatter={(value) => fmtMW(value)}
                />
                <Area
                  type="monotone"
                  dataKey="cumulative"
                  stroke="#d4a017"
                  fill="rgba(212, 160, 23, 0.3)"
                  name="Cumulative Error"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      </section>

      <section className="card panel">
        <h2>Daily accuracy</h2>
        <p className="caption">
          Click column headers to sort. Click a row to inspect that delivery day. <span className="badge-best">Best</span> and{" "}
          <span className="badge-worst">Worst</span> days highlighted.
          Data quality: {detail?.data_quality?.completeness_pct || 0}% complete (
          {detail?.data_quality?.available_periods || 0}/48 periods)
        </p>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th onClick={() => handleSort('delivery_day')} style={{ cursor: 'pointer' }}>
                  Day {tableSort.column === 'delivery_day' && (tableSort.direction === 'asc' ? '↑' : '↓')}
                </th>
                <th onClick={() => handleSort('mae')} style={{ cursor: 'pointer' }}>
                  MAE {tableSort.column === 'mae' && (tableSort.direction === 'asc' ? '↑' : '↓')}
                </th>
                <th onClick={() => handleSort('rmse')} style={{ cursor: 'pointer' }}>
                  RMSE {tableSort.column === 'rmse' && (tableSort.direction === 'asc' ? '↑' : '↓')}
                </th>
                <th onClick={() => handleSort('bias')} style={{ cursor: 'pointer' }}>
                  Bias {tableSort.column === 'bias' && (tableSort.direction === 'asc' ? '↑' : '↓')}
                </th>
                <th onClick={() => handleSort('nmae_pct')} style={{ cursor: 'pointer' }}>
                  nMAE {tableSort.column === 'nmae_pct' && (tableSort.direction === 'asc' ? '↑' : '↓')}
                </th>
                <th onClick={() => handleSort('n')} style={{ cursor: 'pointer' }}>
                  N {tableSort.column === 'n' && (tableSort.direction === 'asc' ? '↑' : '↓')}
                </th>
              </tr>
            </thead>
            <tbody>
              {sortedDaily.map((row) => (
                <tr
                  key={row.delivery_day}
                  className={`${row.delivery_day === day ? "selected" : ""} ${row.isBest ? "best" : ""} ${row.isWorst ? "worst" : ""}`}
                  onClick={() => setDay(row.delivery_day)}
                >
                  <td>
                    {row.delivery_day}
                    {row.isBest && <span className="badge badge-best">Best</span>}
                    {row.isWorst && <span className="badge badge-worst">Worst</span>}
                  </td>
                  <td>{fmtMW(row.metrics.mae)}</td>
                  <td>{fmtMW(row.metrics.rmse)}</td>
                  <td>{fmtMW(row.metrics.bias)}</td>
                  <td>{fmtPct(row.metrics.nmae_pct)}</td>
                  <td>{row.metrics.n}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <p className="footer">
        {meta?.error_band} {meta?.forecast_alignment} Data: Elexon FUELHH and
        WINDFOR only. No login. Gate closure {meta?.gate_closure}.
      </p>
    </div>
  );
}

function Kpi({ label, value, hint, alert }) {
  return (
    <article className={`card kpi ${alert ? 'kpi-alert' : ''}`}>
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      <div className="hint">{hint}</div>
    </article>
  );
}