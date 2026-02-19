"use client";

import { AppShell } from "@/components/shell/AppShell";
import { apiFetch } from "@/lib/api";
import Link from "next/link";
import { use, useEffect, useMemo, useState } from "react";

type AnalysisDetail = {
  id: number;
  source_type: "pdf" | "text";
  source_name: string | null;
  extracted_data: Record<string, any>;
  risk_score: number;
  risk_level: string;
  risk_reasons: string[];
  expected_roi_percent: number;
  rough_cash_gap: number | null;
  verdict: string;
  created_at: string;

  // ✅ NEW
  input_cost_price: number | null;
  input_margin_percent: number | null;
  safe_cost_price: number | null;
};

function VerdictBadge({ verdict }: { verdict: string }) {
  const v = verdict.toLowerCase();
  const cls =
    v.includes("не") ? "bg-red-50 border-red-200 text-red-700" :
    v.includes("осторож") ? "bg-yellow-50 border-yellow-200 text-yellow-800" :
    "bg-green-50 border-green-200 text-green-700";

  return <span className={`inline-flex rounded-full border px-3 py-1 text-xs ${cls}`}>{verdict}</span>;
}

function fmtRub(x: number | null | undefined) {
  if (x === null || x === undefined) return "—";
  return `${Math.round(x).toLocaleString("ru-RU")} ₽`;
}

export default function AnalysisDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const [data, setData] = useState<AnalysisDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const { id } = use(params);


  useEffect(() => {
    apiFetch<AnalysisDetail>(`/analyses/${id}`)
      .then(setData)
      .catch((e) => setError(String(e?.message || e)))
      .finally(() => setLoading(false));
  }, [id]);

  const danger = (data?.extracted_data as any)?.danger_phrases as
    | Array<{
        id: string;
        severity: "high" | "medium" | "low";
        title: string;
        hint: string;
        matches: Array<{ snippet: string; start: number; end: number }>;
      }>
    | undefined;

  const priceIndicator = useMemo(() => {
    if (!data) return null;

    const cost = data.input_cost_price;
    const safe = data.safe_cost_price;

    if (typeof safe !== "number" || safe <= 0) {
      return {
        status: "unknown" as const,
        badge: "⚪ Недостаточно данных",
        text: "Не удалось посчитать безопасную себестоимость — в документе не найдена НМЦК или экстрактор не распознал сумму.",
      };
    }

    if (typeof cost !== "number" || cost <= 0) {
      return {
        status: "unknown" as const,
        badge: "⚪ Нет себестоимости",
        text: "Для сравнения укажи себестоимость при анализе (она сохраняется в отчёт).",
      };
    }

    const ratio = cost / safe;

    if (ratio <= 0.95) {
      return {
        status: "safe" as const,
        badge: "🟢 Цена ок",
        text: "Себестоимость заметно ниже безопасной — по цене проходишь уверенно.",
      };
    }

    if (ratio <= 1.05) {
      return {
        status: "border" as const,
        badge: "🟡 На грани",
        text: "Себестоимость близко к безопасной — ты на грани. Нужен запас/переговоры/оптимизация.",
      };
    }

    return {
      status: "danger" as const,
      badge: "🔴 Опасно",
      text: "Себестоимость выше безопасной — контракт финансово опасен при текущих условиях.",
    };
  }, [data]);
  

  return (
    <AppShell>
      <div className="space-y-4">
        <div className="rounded-2xl border bg-white p-6 shadow-sm">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h1 className="text-xl font-semibold">Анализ #{id}</h1>
              <p className="mt-1 text-sm text-black/60">
                Вердикт, метрики и причины риска.
              </p>
            </div>
            <div className="flex gap-2">
              <Link href="/new" className="rounded-xl bg-black px-4 py-2 text-sm text-white hover:bg-black/90">
                Новый анализ
              </Link>
              <Link href="/history" className="rounded-xl border px-4 py-2 text-sm hover:bg-black/5">
                История
              </Link>
            </div>
          </div>
        </div>

        {loading && (
          <div className="rounded-2xl border bg-white p-6 shadow-sm">Загружаем…</div>
        )}

        {error && (
          <div className="rounded-2xl border border-red-200 bg-red-50 p-6 text-red-700 shadow-sm">
            Ошибка: {error}
          </div>
        )}

        {data && (
          <div className="space-y-4">
            <div className="rounded-2xl border bg-white p-6 shadow-sm">
              <div className="flex items-center justify-between gap-3">
                <VerdictBadge verdict={data.verdict} />
                <div className="text-xs text-black/50">{new Date(data.created_at).toLocaleString()}</div>
              </div>

              <div className="mt-3 grid gap-3 md:grid-cols-4">
                <div className="rounded-xl border p-4">
                  <div className="text-xs text-black/50">Risk Score</div>
                  <div className="mt-1 text-lg font-semibold">{data.risk_score}</div>
                  <div className="text-xs text-black/50">{data.risk_level}</div>
                </div>

                <div className="rounded-xl border p-4">
                  <div className="text-xs text-black/50">ROI</div>
                  <div className="mt-1 text-lg font-semibold">{data.expected_roi_percent}%</div>
                </div>

                <div className="rounded-xl border p-4">
                  <div className="text-xs text-black/50">Кассовый разрыв</div>
                  <div className="mt-1 text-lg font-semibold">
                    {data.rough_cash_gap === null ? "—" : fmtRub(data.rough_cash_gap)}
                  </div>
                  <div className="text-xs text-black/50">оценка грубо</div>
                </div>

                <div className="rounded-xl border p-4">
                  <div className="text-xs text-black/50">Безопасная себестоимость</div>
                  <div className="mt-1 text-lg font-semibold">{fmtRub(data.safe_cost_price)}</div>

                  {priceIndicator && (
                    <>
                      <div className="mt-2 inline-flex items-center rounded-full border px-3 py-1 text-xs">
                        {priceIndicator.badge}
                      </div>
                      <div className="mt-2 text-xs text-black/60">{priceIndicator.text}</div>
                      <div className="mt-2 text-xs text-black/50">
                        Твоя себестоимость: {fmtRub(data.input_cost_price)}
                        {typeof data.input_margin_percent === "number" ? ` • маржа: ${data.input_margin_percent}%` : ""}
                      </div>
                    </>
                  )}
                </div>
              </div>

              {danger?.length ? (
                <div className="mt-4">
                  <div className="text-sm font-medium">Опасные формулировки</div>

                  <div className="mt-2 space-y-3">
                    {danger.map((d, idx) => {
                      const badge =
                        d.severity === "high"
                          ? "🔴 Высокий"
                          : d.severity === "medium"
                          ? "🟡 Средний"
                          : "🟢 Низкий";

                      return (
                        <div key={idx} className="rounded-xl border p-4">
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <div className="text-sm font-semibold">{d.title}</div>
                              <div className="mt-1 text-xs text-black/60">{d.hint}</div>
                            </div>

                            <span className="inline-flex rounded-full border px-3 py-1 text-xs text-black/70">
                              {badge}
                            </span>
                          </div>

                          {d.matches?.length ? (
                            <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-black/70">
                              {d.matches.slice(0, 3).map((m, i) => (
                                <li key={i}>{m.snippet}</li>
                              ))}
                            </ul>
                          ) : null}
                        </div>
                      );
                    })}
                  </div>
                </div>
              ) : null}

              <div className="mt-4">
                <div className="text-sm font-medium">Причины риска</div>
                <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-black/70">
                  {data.risk_reasons?.length
                    ? data.risk_reasons.map((r, i) => <li key={i}>{r}</li>)
                    : <li>Причины не указаны</li>}
                </ul>
              </div>
            </div>

            <details className="rounded-2xl border bg-white p-6 shadow-sm">
              <summary className="cursor-pointer text-sm font-medium">Извлечённые данные (JSON)</summary>
              <pre className="mt-3 overflow-auto rounded-xl bg-black/5 p-3 text-xs">
                {JSON.stringify(data.extracted_data, null, 2)}
              </pre>
            </details>
          </div>
        )}
      </div>
    </AppShell>
  );
}
