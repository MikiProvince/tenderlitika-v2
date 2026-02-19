import type { AnalysisViewModel } from "./types";
import { formatPercent, formatRUB } from "./format";

function Stat({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div className="min-w-0">
      <div className="text-xs font-medium text-slate-500">{label}</div>
      <div className="mt-1 truncate text-xl font-semibold tracking-tight text-slate-900">
        {value}
      </div>
      {hint && <div className="mt-1 text-xs text-slate-500">{hint}</div>}
    </div>
  );
}

export default function FinancialSnapshot({ analysis }: { analysis: AnalysisViewModel }) {
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5">
      <div className="grid grid-cols-2 gap-5 sm:grid-cols-4">
        <Stat
          label="Безопасная себестоимость"
          value={formatRUB(analysis.safeCostPrice)}
          hint="расчёт по условиям"
        />
        <Stat
          label="Твоя себестоимость"
          value={formatRUB(analysis.inputCostPrice)}
          hint={
            analysis.inputMarginPercent != null
              ? `маржа: ${formatPercent(analysis.inputMarginPercent)}`
              : undefined
          }
        />
        <Stat
          label="Кассовый разрыв"
          value={formatRUB(analysis.roughCashGap)}
          hint="оценка грубо"
        />
        <Stat
          label="Ожидаемый ROI"
          value={
            analysis.expectedRoiPercent != null
              ? formatPercent(analysis.expectedRoiPercent)
              : "—"
          }
        />
      </div>
    </section>
  );
}
