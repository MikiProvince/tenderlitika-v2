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
    <div className="min-w-0 rounded-xl border border-[var(--border)] bg-[var(--surface-muted)] p-3">
      <div className="text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">{label}</div>
      <div className="mt-1 truncate text-xl font-semibold tracking-tight text-slate-900">{value}</div>
      {hint && <div className="mt-1 text-xs text-[var(--muted)]">{hint}</div>}
    </div>
  );
}

export default function FinancialSnapshot({ analysis }: { analysis: AnalysisViewModel }) {
  return (
    <section id="financial-snapshot" className="surface-card p-5">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-slate-900">Финансовый срез</h2>
          <p className="mt-1 text-xs text-[var(--muted)]">Ключевые цифры для решения по участию в тендере.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Безопасная себестоимость" value={formatRUB(analysis.safeCostPrice)} hint="Оценка по условиям контракта" />

        <Stat
          label="Ваша себестоимость"
          value={formatRUB(analysis.inputCostPrice)}
          hint={analysis.inputMarginPercent != null ? `Плановая маржа: ${formatPercent(analysis.inputMarginPercent)}` : undefined}
        />

        <Stat label="Кассовый разрыв" value={formatRUB(analysis.roughCashGap)} hint="Оценка оборотной потребности" />

        <Stat label="Ожидаемый ROI" value={analysis.expectedRoiPercent != null ? formatPercent(analysis.expectedRoiPercent) : "—"} />
      </div>
    </section>
  );
}
