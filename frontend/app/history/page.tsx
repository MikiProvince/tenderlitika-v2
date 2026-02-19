"use client";

import { AppShell } from "@/components/shell/AppShell";
import { useEffect, useMemo, useState } from "react";
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

function riskTone(score: number): string {
  if (score >= 9) return "bg-red-100 text-red-700";
  if (score >= 7) return "bg-orange-100 text-orange-700";
  if (score >= 4) return "bg-amber-100 text-amber-700";
  return "bg-emerald-100 text-emerald-700";
}

export default function HistoryPage() {
  const [items, setItems] = useState<Analysis[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [clearingAll, setClearingAll] = useState(false);

  useEffect(() => {
    apiFetch<Analysis[]>("/analyses")
      .then(setItems)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, []);

  const avgRisk = useMemo(() => {
    if (!items.length) return null;
    const sum = items.reduce((acc, item) => acc + item.risk_score, 0);
    return Number((sum / items.length).toFixed(1));
  }, [items]);

  async function onDeleteOne(id: number) {
    if (!window.confirm(`Удалить анализ #${id}?`)) return;

    setActionError(null);
    setDeletingId(id);

    try {
      await apiFetch<{ ok: boolean }>(`/analyses/${id}`, { method: "DELETE" });
      setItems((prev) => prev.filter((item) => item.id !== id));
    } catch (e: unknown) {
      setActionError(e instanceof Error ? e.message : String(e));
    } finally {
      setDeletingId(null);
    }
  }

  async function onClearAll() {
    if (!items.length) return;
    if (!window.confirm(`Удалить всю историю анализов (${items.length} шт.)?`)) return;

    setActionError(null);
    setClearingAll(true);

    try {
      await apiFetch<{ ok: boolean; deleted_count: number }>("/analyses", { method: "DELETE" });
      setItems([]);
    } catch (e: unknown) {
      setActionError(e instanceof Error ? e.message : String(e));
    } finally {
      setClearingAll(false);
    }
  }

  return (
    <AppShell>
      <div className="space-y-4">
        <section className="surface-card p-6">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h1 className="text-xl font-semibold tracking-tight">История анализов</h1>
              <p className="mt-1 text-sm text-[var(--muted)]">Сохранённые расчёты и быстрый доступ к деталям по каждому тендеру.</p>
            </div>

            <div className="flex gap-2">
              <div className="status-chip px-3 py-1 text-xs text-[var(--muted)]">Всего: {items.length}</div>
              <div className="status-chip px-3 py-1 text-xs text-[var(--muted)]">Средний риск: {avgRisk ?? "—"}</div>
              <button
                className="rounded-xl border border-red-200 bg-red-50 px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-60"
                onClick={onClearAll}
                disabled={!items.length || clearingAll || loading}
              >
                {clearingAll ? "Удаляем..." : "Очистить историю"}
              </button>
              <Link href="/new" className="btn-primary px-3 py-1.5 text-xs font-medium">
                Новый анализ
              </Link>
            </div>
          </div>
        </section>

        {loading && <section className="surface-card p-5 text-sm text-[var(--muted)]">Загружаем историю...</section>}

        {error && (
          <section className="surface-card border-red-200 bg-red-50 p-5 text-sm text-red-700">
            Ошибка загрузки истории: {error}
          </section>
        )}

        {actionError && (
          <section className="surface-card border-red-200 bg-red-50 p-5 text-sm text-red-700">
            Ошибка операции: {actionError}
          </section>
        )}

        {!loading && !items.length && !error && (
          <section className="surface-card p-5 text-sm text-[var(--muted)]">
            Пока нет анализов. Запустите первый расчёт, чтобы сформировать историю решений.
          </section>
        )}

        {items.map((a) => (
          <section key={a.id} className="surface-card p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="text-xs text-[var(--muted)]">{a.source_name ?? "Текстовый анализ"}</div>
                <div className="mt-1 text-base font-semibold text-slate-900">{a.verdict}</div>

                <div className="mt-3 flex flex-wrap gap-2 text-xs">
                  <span className={`rounded-full px-2.5 py-1 font-semibold ${riskTone(a.risk_score)}`}>Риск {a.risk_score}/10</span>
                  <span className="status-chip px-2.5 py-1">ROI: {a.expected_roi_percent}%</span>
                  <span className="status-chip px-2.5 py-1">{new Date(a.created_at).toLocaleString("ru-RU")}</span>
                </div>
              </div>

              <div className="flex gap-2 self-start">
                <Link href={`/analysis/${a.id}`} className="btn-secondary px-3 py-1.5 text-xs font-medium">
                  Открыть #{a.id}
                </Link>
                <button
                  className="rounded-xl border border-red-200 bg-red-50 px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-60"
                  onClick={() => onDeleteOne(a.id)}
                  disabled={deletingId === a.id || clearingAll}
                >
                  {deletingId === a.id ? "Удаляем..." : "Удалить"}
                </button>
              </div>
            </div>
          </section>
        ))}
      </div>
    </AppShell>
  );
}
