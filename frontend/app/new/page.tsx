"use client";

import { AppShell } from "@/components/shell/AppShell";
import { apiFetch } from "@/lib/api";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

type AnalyzeResponse = {
  analysis_id: number;
  extracted_data: Record<string, unknown>;
  risk_score: number;
  risk_level: string;
  risk_reasons: string[];
  expected_roi_percent: number;
  rough_cash_gap: number | null;
  verdict: string;
};

const LS_COST = "tlk_cost_price";
const LS_MARGIN = "tlk_margin";
const STAGES = ["Извлечение условий", "Расчёт рисков и финансов", "Формирование отчёта"];

export default function NewAnalysisPage() {
  const router = useRouter();

  const [text, setText] = useState("");
  const [cost, setCost] = useState("1000000");
  const [margin, setMargin] = useState("15");

  const [loading, setLoading] = useState(false);
  const [stageIndex, setStageIndex] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const savedCost = localStorage.getItem(LS_COST);
    const savedMargin = localStorage.getItem(LS_MARGIN);
    if (savedCost) setCost(savedCost);
    if (savedMargin) setMargin(savedMargin);
  }, []);

  function validate() {
    const parsedCost = Number(cost);
    const parsedMargin = Number(margin);

    if (!text.trim()) return "Вставьте текст тендера перед запуском анализа.";
    if (!Number.isFinite(parsedCost) || parsedCost <= 0) return "Себестоимость должна быть больше 0.";
    if (!Number.isFinite(parsedMargin) || parsedMargin < 0 || parsedMargin > 100) return "Маржа должна быть в диапазоне 0–100%.";

    return null;
  }

  async function onAnalyze() {
    const validationError = validate();
    if (validationError) {
      setError(validationError);
      return;
    }

    setError(null);
    setLoading(true);
    setStageIndex(0);

    try {
      localStorage.setItem(LS_COST, cost);
      localStorage.setItem(LS_MARGIN, margin);

      const payload = {
        text: text.trim(),
        cost_price: Number(cost),
        planned_margin_percent: Number(margin),
      };

      setStageIndex(1);
      const res = await apiFetch<AnalyzeResponse>("/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      setStageIndex(2);
      router.push(`/analysis/${res.analysis_id}`);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);

      if (msg.includes("Missing X-API-Key") || msg.includes("Invalid API key") || msg.includes("401")) {
        setError("API-ключ не задан или неверный. Перейдите в раздел входа и обновите ключ.");
      } else if (msg.includes("Quota exceeded") || msg.includes("429")) {
        setError("Лимит анализов исчерпан. Дождитесь сброса лимита или обновите тариф.");
      } else {
        setError(msg);
      }
    } finally {
      setLoading(false);
      setStageIndex(null);
    }
  }

  return (
    <AppShell>
      <div className="space-y-4">
        <section className="surface-card p-6">
          <h1 className="text-xl font-semibold tracking-tight">Новый анализ</h1>
          <p className="mt-1 text-sm text-[var(--muted)]">
            Вставьте текст закупки и финансовые параметры. Сервис рассчитает риск, ROI и ориентир безопасной цены.
          </p>
        </section>

        <section className="grid gap-4 md:grid-cols-2">
          <div className="surface-card p-4">
            <label htmlFor="tender-text" className="block text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
              Текст тендера
            </label>
            <textarea
              id="tender-text"
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Вставьте сюда текст документа или ключевые разделы закупки..."
              className="mt-2 h-72 w-full resize-none rounded-xl border border-[var(--border)] bg-white p-3 text-sm outline-none focus-visible:border-[var(--brand)]"
            />
            <div className="mt-2 text-xs text-[var(--muted)]">
              Лучше всего работают фрагменты с оплатой, сроками поставки, обеспечением и штрафами.
            </div>
          </div>

          <div className="space-y-4">
            <div className="surface-card p-4">
              <label htmlFor="cost" className="block text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
                Себестоимость (₽)
              </label>
              <input
                id="cost"
                value={cost}
                onChange={(e) => setCost(e.target.value)}
                inputMode="decimal"
                className="mt-2 w-full rounded-xl border border-[var(--border)] bg-white p-3 text-sm outline-none focus-visible:border-[var(--brand)]"
              />

              <label htmlFor="margin" className="mt-4 block text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
                Плановая маржа (%)
              </label>
              <input
                id="margin"
                value={margin}
                onChange={(e) => setMargin(e.target.value)}
                inputMode="decimal"
                className="mt-2 w-full rounded-xl border border-[var(--border)] bg-white p-3 text-sm outline-none focus-visible:border-[var(--brand)]"
              />

              {error && <div className="mt-4 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}

              <button
                disabled={loading}
                className="btn-primary mt-4 w-full px-4 py-3 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-60"
                onClick={onAnalyze}
              >
                {loading ? "Выполняем анализ..." : "Запустить анализ"}
              </button>

              <div className="mt-2 text-xs text-[var(--muted)]">Результат автоматически сохраняется в истории.</div>
            </div>

            <div className="surface-card p-4" aria-live="polite">
              <div className="text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">Прогресс</div>
              <div className="mt-3 space-y-2">
                {STAGES.map((stage, idx) => {
                  const isDone = stageIndex !== null && idx < stageIndex;
                  const isCurrent = stageIndex === idx;

                  return (
                    <div key={stage} className="flex items-center gap-2 text-sm">
                      <span
                        className={[
                          "inline-flex h-6 w-6 items-center justify-center rounded-full border text-xs font-semibold",
                          isDone ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "",
                          isCurrent ? "border-[var(--brand)] bg-blue-50 text-[var(--brand)]" : "",
                          !isDone && !isCurrent ? "border-[var(--border)] bg-white text-[var(--muted)]" : "",
                        ].join(" ")}
                      >
                        {isDone ? "✓" : idx + 1}
                      </span>
                      <span className={isCurrent ? "font-medium text-slate-900" : "text-[var(--muted)]"}>{stage}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </section>
      </div>
    </AppShell>
  );
}
