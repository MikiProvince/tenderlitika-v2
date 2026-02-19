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

export default function NewAnalysisPage() {
  const router = useRouter();

  const [text, setText] = useState("");
  const [cost, setCost] = useState("1000000");
  const [margin, setMargin] = useState("15");

  const [loading, setLoading] = useState(false);
  const [step, setStep] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const c = localStorage.getItem(LS_COST);
    const m = localStorage.getItem(LS_MARGIN);
    if (c) setCost(c);
    if (m) setMargin(m);
  }, []);

  function validate() {
    const c = Number(cost);
    const m = Number(margin);
    if (!text.trim()) return "Вставь текст тендера.";
    if (!Number.isFinite(c) || c <= 0) return "Себестоимость должна быть > 0.";
    if (!Number.isFinite(m) || m < 0 || m > 100) return "Маржа должна быть от 0 до 100.";
    return null;
  }

  async function onAnalyze() {
    const v = validate();
    if (v) {
      setError(v);
      return;
    }

    setError(null);
    setLoading(true);

    try {
      localStorage.setItem(LS_COST, cost);
      localStorage.setItem(LS_MARGIN, margin);

      setStep("Извлекаем условия…");

      const payload = {
        text: text.trim(),
        cost_price: Number(cost),
        planned_margin_percent: Number(margin),
      };

      setStep("Считаем риски и деньги…");

      const res = await apiFetch<AnalyzeResponse>("/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      setStep("Готово. Открываем отчёт…");
      router.push(`/analysis/${res.analysis_id}`);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);

      // дружелюбные ошибки
      if (msg.includes("Missing X-API-Key") || msg.includes("Invalid API key") || msg.includes("401")) {
        setError("Похоже, API key не задан или неверный. Зайди в /login и вставь ключ.");
      } else if (msg.includes("Quota exceeded") || msg.includes("429")) {
        setError("Лимит анализов исчерпан (429). Подожди сброс лимита или обнови тариф.");
      } else {
        setError(msg);
      }
    } finally {
      setLoading(false);
      setStep(null);
    }
  }

  return (
    <AppShell>
      <div className="space-y-4">
        <div className="rounded-2xl border bg-white p-6 shadow-sm">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h1 className="text-xl font-semibold">Новый анализ (текст)</h1>
              <p className="mt-1 text-sm text-black/60">
                Вставь текст тендера. Себестоимость и маржа нужны для расчёта ROI и кассового разрыва.
              </p>
            </div>
          </div>

          <div className="mt-5 grid gap-4 md:grid-cols-2">
            <div className="rounded-2xl border p-4">
              <label className="block text-xs font-medium text-black/60">Текст тендера</label>
              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="Вставь сюда текст документа/закупки…"
                className="mt-2 h-56 w-full resize-none rounded-xl border p-3 text-sm outline-none focus:ring-2 focus:ring-black/10"
              />
              <div className="mt-2 text-xs text-black/50">
                Совет: можно вставлять кусками — главное, чтобы были сроки/оплата/обеспечение/штрафы.
              </div>
            </div>

            <div className="rounded-2xl border p-4">
              <label className="block text-xs font-medium text-black/60">Себестоимость (₽)</label>
              <input
                value={cost}
                onChange={(e) => setCost(e.target.value)}
                className="mt-2 w-full rounded-xl border p-3 text-sm outline-none focus:ring-2 focus:ring-black/10"
              />

              <label className="mt-4 block text-xs font-medium text-black/60">Маржа (%)</label>
              <input
                value={margin}
                onChange={(e) => setMargin(e.target.value)}
                className="mt-2 w-full rounded-xl border p-3 text-sm outline-none focus:ring-2 focus:ring-black/10"
              />

              {error && (
                <div className="mt-4 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">
                  {error}
                </div>
              )}

              <button
                disabled={loading}
                className={[
                  "mt-4 w-full rounded-xl px-4 py-3 text-sm text-white",
                  loading ? "bg-black/50" : "bg-black hover:bg-black/90",
                ].join(" ")}
                onClick={onAnalyze}
              >
                {loading ? "Анализируем…" : "Анализировать"}
              </button>

              {step && <div className="mt-2 text-xs text-black/60">{step}</div>}

              <div className="mt-2 text-xs text-black/50">
                Результат сохранится в истории автоматически.
              </div>
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
