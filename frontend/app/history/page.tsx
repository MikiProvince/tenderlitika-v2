"use client";

import { AppShell } from "@/components/shell/AppShell";
import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import Link from "next/link";

type Analysis = {
  id: number;
  source_type: "pdf" | "text";
  source_name: string | null;
  risk_score: number;
  risk_level: string;
  expected_roi_percent: number;
  rough_cash_gap: number | null;
  verdict: string;
  created_at: string;
};

export default function HistoryPage() {
  const [items, setItems] = useState<Analysis[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<Analysis[]>("/analyses")
      .then(setItems)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  return (
    <AppShell>
      <div className="space-y-4">

        <div className="rounded-2xl border bg-white p-6 shadow-sm">
          <div className="flex items-start justify-between">
            <div>
              <h1 className="text-xl font-semibold">История анализов</h1>
              <p className="mt-1 text-sm text-black/60">
                Все ваши сохранённые расчёты.
              </p>
            </div>

            <Link
              href="/new"
              className="rounded-xl bg-black px-4 py-2 text-sm text-white hover:bg-black/90"
            >
              Новый анализ
            </Link>
          </div>
        </div>

        {loading && (
          <div className="rounded-2xl border bg-white p-6 shadow-sm">
            Загружаем…
          </div>
        )}

        {error && (
          <div className="rounded-2xl border bg-red-50 p-6 shadow-sm text-red-700">
            Ошибка: {error}
          </div>
        )}

        {!loading && !items.length && (
          <div className="rounded-2xl border bg-white p-6 shadow-sm text-black/60">
            Пока нет анализов.
          </div>
        )}

        {items.map((a) => (
          <div key={a.id} className="rounded-2xl border bg-white p-5 shadow-sm">

            <div className="flex justify-between gap-4">

              <div>
                <div className="text-sm text-black/50">
                  {a.source_name ?? "Текстовый анализ"}
                </div>

                <div className="mt-1 text-lg font-semibold">
                  {a.verdict}
                </div>

                <div className="mt-2 text-sm text-black/60">
                  Risk: {a.risk_score} | ROI: {a.expected_roi_percent}%
                </div>
              </div>

              <Link
                href={`/analysis/${a.id}`}
                className="self-start rounded-xl border px-3 py-1 text-sm hover:bg-black/5"
              >
                Открыть
              </Link>

            </div>

          </div>
        ))}

      </div>
    </AppShell>
  );
}
