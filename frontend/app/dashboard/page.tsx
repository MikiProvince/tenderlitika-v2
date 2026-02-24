"use client";

import { AppShell } from "@/components/shell/AppShell";
import { apiFetch } from "@/lib/api";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

type Analysis = {
  id: number;
  source_type: "pdf" | "text" | "doc" | "docx" | "batch";
  source_name: string | null;
  risk_score: number;
  risk_level: string;
  expected_roi_percent: number;
  rough_cash_gap: number | null;
  verdict: string;
  created_at: string;
};

const MONTH_LIMIT = 30;

function isHighRisk(item: Analysis): boolean {
  const lvl = item.risk_level.toLowerCase();
  return item.risk_score >= 8 || lvl.includes("high") || lvl.includes("critical") || lvl.includes("высок") || lvl.includes("крит");
}

function sourceLabel(item: Analysis): string {
  if (item.source_name) return item.source_name;
  if (item.source_type === "batch") return "Пакет документов";
  if (item.source_type === "doc" || item.source_type === "docx") return "Документ";
  if (item.source_type === "pdf") return "PDF-документ";
  return "Текстовый анализ";
}

export default function DashboardPage() {
  const [items, setItems] = useState<Analysis[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<Analysis[]>("/analyses")
      .then(setItems)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, []);

  const latest = items[0] ?? null;

  const avgRisk = useMemo(() => {
    if (!items.length) return null;
    const sum = items.reduce((acc, item) => acc + item.risk_score, 0);
    return Number((sum / items.length).toFixed(1));
  }, [items]);

  const highRiskCount = useMemo(() => items.filter(isHighRisk).length, [items]);
  const usedThisMonth = Math.min(items.length, MONTH_LIMIT);
  const usagePct = Math.min(100, Math.round((usedThisMonth / MONTH_LIMIT) * 100));

  return (
    <AppShell>
      <div className="space-y-4">
        <section className="surface-card p-6">
          <h1 className="text-2xl font-semibold tracking-tight">Обзор</h1>
          <p className="mt-1 text-sm text-[var(--muted)]">
            Аналитика по вашим тендерам: текущая загрузка лимита, профиль рисков и быстрый переход к новому разбору.
          </p>

          <div className="mt-5 flex flex-wrap gap-2">
            <Link href="/new" className="btn-primary px-4 py-2 text-sm font-medium">
              Новый анализ
            </Link>
            <Link href="/history" className="btn-secondary px-4 py-2 text-sm font-medium">
              История анализов
            </Link>
          </div>
        </section>

        {error && (
          <section className="surface-card border-red-200 bg-red-50 p-5 text-sm text-red-700">
            Не удалось загрузить данные: {error}
            <div className="mt-3">
              <Link href="/login" className="btn-secondary inline-flex px-3 py-1.5 text-xs font-medium">
                Проверить API-ключ
              </Link>
            </div>
          </section>
        )}

        <section className="grid gap-4 md:grid-cols-3">
          <div className="surface-card p-5">
            <div className="text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">Лимит анализов</div>
            <div className="mt-2 text-2xl font-semibold tracking-tight">{usedThisMonth} / {MONTH_LIMIT}</div>
            <div className="mt-3 h-2 rounded-full bg-slate-100">
              <div className="h-2 rounded-full bg-[var(--brand)]" style={{ width: `${usagePct}%` }} />
            </div>
            <div className="mt-2 text-xs text-[var(--muted)]">Использовано {usagePct}% месячного лимита</div>
          </div>

          <div className="surface-card p-5">
            <div className="text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">Средний риск</div>
            <div className="mt-2 text-2xl font-semibold tracking-tight">{loading ? "—" : avgRisk ?? "—"}</div>
            <div className="mt-2 text-xs text-[var(--muted)]">По всем завершенным анализам</div>
          </div>

          <div className="surface-card p-5">
            <div className="text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">Высокий риск</div>
            <div className="mt-2 text-2xl font-semibold tracking-tight">{loading ? "—" : highRiskCount}</div>
            <div className="mt-2 text-xs text-[var(--muted)]">Анализов с индексом риска 8+ или критичным уровнем</div>
          </div>
        </section>

        <section className="surface-card p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold">Последний анализ</h2>
              <p className="mt-1 text-sm text-[var(--muted)]">Быстрый доступ к самому свежему результату.</p>
            </div>

            {latest && (
              <Link href={`/analysis/${latest.id}`} className="btn-secondary px-3 py-1.5 text-xs font-medium">
                Открыть #{latest.id}
              </Link>
            )}
          </div>

          {loading && <div className="mt-4 surface-muted p-4 text-sm text-[var(--muted)]">Загружаем историю анализов...</div>}

          {!loading && latest && (
            <div className="mt-4 surface-muted p-4">
              <div className="flex flex-wrap items-center gap-2">
                <div className="rounded-full bg-white px-2.5 py-1 text-xs font-semibold text-slate-600">Риск {latest.risk_score}/10</div>
                <div className="rounded-full bg-white px-2.5 py-1 text-xs text-slate-600">{new Date(latest.created_at).toLocaleString("ru-RU")}</div>
              </div>
              <div className="mt-3 text-sm font-semibold text-slate-900">{latest.verdict}</div>
              <div className="mt-1 text-sm text-[var(--muted)]">Источник: {sourceLabel(latest)}</div>
            </div>
          )}

          {!loading && !latest && !error && (
            <div className="mt-4 surface-muted p-4 text-sm text-[var(--muted)]">
              Пока нет сохраненных анализов. Запустите первый разбор, чтобы увидеть показатели и динамику рисков.
            </div>
          )}
        </section>
      </div>
    </AppShell>
  );
}