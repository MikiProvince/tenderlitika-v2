"use client";

import { AppShell } from "@/components/shell/AppShell";
import { apiFetch } from "@/lib/api";
import Link from "next/link";
import { useEffect, useState } from "react";

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
};

function VerdictBadge({ verdict }: { verdict: string }) {
  const v = verdict.toLowerCase();
  const cls =
    v.includes("не") ? "bg-red-50 border-red-200 text-red-700" :
    v.includes("осторож") ? "bg-yellow-50 border-yellow-200 text-yellow-800" :
    "bg-green-50 border-green-200 text-green-700";

  return <span className={`inline-flex rounded-full border px-3 py-1 text-xs ${cls}`}>{verdict}</span>;
}

export default function AnalysisDetailPage({ params }: { params: { id: string } }) {
  const [data, setData] = useState<AnalysisDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiFetch<AnalysisDetail>(`/analyses/${params.id}`)
      .then(setData)
      .catch((e) => setError(String(e?.message || e)))
      .finally(() => setLoading(false));
  }, [params.id]);

  return (
    <AppShell>
      <div className="space-y-4">
        <div className="rounded-2xl border bg-white p-6 shadow-sm">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h1 className="text-xl font-semibold">Анализ #{params.id}</h1>
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

              <div className="mt-3 grid gap-3 md:grid-cols-3">
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
                    {data.rough_cash_gap === null ? "—" : `${data.rough_cash_gap}`}
                  </div>
                  <div className="text-xs text-black/50">оценка грубо</div>
                </div>
              </div>

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
