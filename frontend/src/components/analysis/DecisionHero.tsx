import type { AnalysisViewModel, RiskLevel } from "./types";
import { formatDateTimeRu } from "./format";

function tone(level: RiskLevel) {
  switch (level) {
    case "critical":
      return { badge: "bg-red-600 text-white", panel: "border-red-200 bg-red-50", title: "text-red-900", sub: "text-red-800" };
    case "high":
      return { badge: "bg-orange-600 text-white", panel: "border-orange-200 bg-orange-50", title: "text-orange-900", sub: "text-orange-800" };
    case "medium":
      return { badge: "bg-amber-600 text-white", panel: "border-amber-200 bg-amber-50", title: "text-amber-900", sub: "text-amber-800" };
    default:
      return { badge: "bg-slate-700 text-white", panel: "border-slate-200 bg-slate-50", title: "text-slate-900", sub: "text-slate-700" };
  }
}

function decisionLabel(level: RiskLevel) {
  if (level === "critical" || level === "high") return "НЕ УЧАСТВОВАТЬ";
  if (level === "medium") return "С ОСТОРОЖНОСТЬЮ";
  return "МОЖНО УЧАСТВОВАТЬ";
}

export default function DecisionHero({ analysis }: { analysis: AnalysisViewModel }) {
  const t = tone(analysis.riskLevel);
  const decision = decisionLabel(analysis.riskLevel);

  const primaryFactor =
    analysis.roughCashGap && analysis.roughCashGap > 0
      ? `кассовый разрыв ~ ${Math.round(analysis.roughCashGap).toLocaleString("ru-RU")} ₽`
      : analysis.primaryRisks?.[0]?.title || "условия контракта создают повышенный риск";

  return (
    <section className={`rounded-2xl border p-6 ${t.panel}`}>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold ${t.badge}`}>
              {decision}
            </span>
            <span className="text-xs text-slate-600">
              Анализ #{analysis.id} • {formatDateTimeRu(analysis.createdAt)}
            </span>
          </div>

          <h1 className={`text-3xl font-semibold tracking-tight leading-tight ${t.title}`}>
            {analysis.verdict}
          </h1>

          <p className={`text-sm ${t.sub}`}>
            Основной фактор: <span className="font-semibold">{primaryFactor}</span>
          </p>

          {typeof analysis.confidence === "number" && (
            <div className="pt-2">
              <div className="flex items-center justify-between text-xs text-slate-600">
                <span>Уверенность анализа</span>
                <span>{Math.round(analysis.confidence * 100)}%</span>
              </div>
              <div className="mt-1 h-2 w-full rounded-full bg-white/60">
                <div className="h-2 rounded-full bg-slate-900/70" style={{ width: `${Math.round(analysis.confidence * 100)}%` }} />
              </div>
            </div>
          )}
        </div>

        <div className="flex flex-col gap-2 sm:items-end">
          <div className="flex gap-2">
            <button className="rounded-xl bg-black px-4 py-2 text-sm font-semibold text-white hover:opacity-90">
              Безопасная цена
            </button>
            <button className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-900 hover:bg-slate-50">
              Скачать отчёт
            </button>
          </div>
          <div className="text-xs text-slate-600">
            Risk score: <span className="font-semibold">{analysis.riskScore}</span> / 10
          </div>
        </div>
      </div>
    </section>
  );
}
