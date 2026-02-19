"use client";

import type { AnalysisViewModel, RiskLevel } from "./types";
import { formatDateTimeRu, formatPercent, formatRUB } from "./format";

function tone(level: RiskLevel) {
  switch (level) {
    case "critical":
      return {
        badge: "bg-red-600 text-white",
        panel: "border-red-200 bg-red-50",
        title: "text-red-900",
        sub: "text-red-800",
      };
    case "high":
      return {
        badge: "bg-orange-600 text-white",
        panel: "border-orange-200 bg-orange-50",
        title: "text-orange-900",
        sub: "text-orange-800",
      };
    case "medium":
      return {
        badge: "bg-amber-600 text-white",
        panel: "border-amber-200 bg-amber-50",
        title: "text-amber-900",
        sub: "text-amber-800",
      };
    default:
      return {
        badge: "bg-emerald-600 text-white",
        panel: "border-emerald-200 bg-emerald-50",
        title: "text-emerald-900",
        sub: "text-emerald-800",
      };
  }
}

function decisionLabel(level: RiskLevel) {
  if (level === "critical" || level === "high") return "Не участвовать";
  if (level === "medium") return "Участвовать с осторожностью";
  return "Можно участвовать";
}

function riskLevelLabel(level: RiskLevel) {
  switch (level) {
    case "critical":
      return "критический";
    case "high":
      return "высокий";
    case "medium":
      return "средний";
    default:
      return "низкий";
  }
}

function downloadReport(analysis: AnalysisViewModel) {
  const lines = [
    `Tenderlitika • Анализ #${analysis.id}`,
    `Дата: ${formatDateTimeRu(analysis.createdAt)}`,
    `Решение: ${decisionLabel(analysis.riskLevel)}`,
    `Вердикт: ${analysis.verdict}`,
    `Индекс риска: ${analysis.riskScore}/10`,
    `Ожидаемый ROI: ${formatPercent(analysis.expectedRoiPercent)}`,
    `Кассовый разрыв: ${formatRUB(analysis.roughCashGap)}`,
    `Безопасная себестоимость: ${formatRUB(analysis.safeCostPrice)}`,
    "",
    "Ключевые риски:",
    ...(analysis.primaryRisks.length
      ? analysis.primaryRisks.map((risk, idx) => `${idx + 1}. ${risk.title}`)
      : ["1. Не выделено"]),
    "",
    "Рекомендации:",
    ...(analysis.fixSuggestions.length
      ? analysis.fixSuggestions.map((item, idx) => `${idx + 1}. ${item}`)
      : ["1. Нет рекомендаций"]),
  ];

  const blob = new Blob([lines.join("\n")], { type: "text/plain;charset=utf-8" });
  const href = URL.createObjectURL(blob);
  const fileName = `tenderlitika-analysis-${analysis.id}.txt`;

  const link = document.createElement("a");
  link.href = href;
  link.download = fileName;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(href);
}

export default function DecisionHero({ analysis }: { analysis: AnalysisViewModel }) {
  const t = tone(analysis.riskLevel);
  const decision = decisionLabel(analysis.riskLevel);

  const primaryFactor =
    analysis.roughCashGap && analysis.roughCashGap > 0
      ? `Кассовый разрыв ~ ${Math.round(analysis.roughCashGap).toLocaleString("ru-RU")} ₽`
      : analysis.primaryRisks?.[0]?.title || "Условия контракта создают повышенный риск";

  return (
    <section className={`rounded-2xl border p-6 ${t.panel}`}>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold ${t.badge}`}>{decision}</span>
            <span className="text-xs text-slate-600">
              Анализ #{analysis.id} • {formatDateTimeRu(analysis.createdAt)}
            </span>
          </div>

          <h1 className={`text-2xl font-semibold leading-tight tracking-tight sm:text-3xl ${t.title}`}>{analysis.verdict}</h1>

          <p className={`text-sm ${t.sub}`}>
            Основной фактор: <span className="font-semibold">{primaryFactor}</span>
          </p>

          <div className="flex flex-wrap gap-2 text-xs text-slate-700">
            <span className="rounded-full bg-white/80 px-2.5 py-1">Индекс риска: {analysis.riskScore}/10</span>
            <span className="rounded-full bg-white/80 px-2.5 py-1">ROI: {formatPercent(analysis.expectedRoiPercent)}</span>
            <span className="rounded-full bg-white/80 px-2.5 py-1">Разрыв: {formatRUB(analysis.roughCashGap)}</span>
          </div>

          {typeof analysis.confidence === "number" && (
            <div className="pt-1">
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
            <button
              className="group inline-flex items-center gap-2 rounded-xl border border-blue-500/40 bg-gradient-to-r from-[var(--brand)] to-[#2f6cb0] px-4 py-2 text-sm font-semibold text-white shadow-sm hover:-translate-y-0.5 hover:from-[var(--brand-strong)] hover:to-[#225387] hover:shadow-lg"
              onClick={() => downloadReport(analysis)}
            >
              <svg
                aria-hidden="true"
                viewBox="0 0 20 20"
                className="h-4 w-4 transition-transform group-hover:translate-y-0.5"
                fill="currentColor"
              >
                <path d="M10 2a1 1 0 011 1v7.59l2.3-2.3a1 1 0 111.4 1.42l-4 3.99a1 1 0 01-1.4 0l-4-3.99a1 1 0 111.4-1.42l2.3 2.3V3a1 1 0 011-1z" />
                <path d="M4 15a1 1 0 011-1h10a1 1 0 110 2H5a1 1 0 01-1-1z" />
              </svg>
              Скачать отчёт
            </button>
          </div>
          <div className="text-xs text-slate-600">
            Риск-профиль: <span className="font-semibold">{riskLevelLabel(analysis.riskLevel)}</span>
          </div>
        </div>
      </div>
    </section>
  );
}
