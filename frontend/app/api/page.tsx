"use client";

import { AppShell } from "@/components/shell/AppShell";
import { apiFetch } from "@/lib/api";
import { getApiKey, subscribeToApiKey } from "@/lib/storage";
import Link from "next/link";
import { useEffect, useMemo, useState, useSyncExternalStore } from "react";

type Analysis = { id: number };

const MONTH_LIMIT = 30;

export default function ApiPage() {
  const hasKey = useSyncExternalStore(subscribeToApiKey, () => !!getApiKey(), () => false);
  const [count, setCount] = useState<number>(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiFetch<Analysis[]>("/analyses")
      .then((items) => setCount(items.length))
      .catch(() => setCount(0))
      .finally(() => setLoading(false));
  }, []);

  const usedThisMonth = Math.min(count, MONTH_LIMIT);
  const usagePct = useMemo(() => Math.min(100, Math.round((usedThisMonth / MONTH_LIMIT) * 100)), [usedThisMonth]);
  const apiBase = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

  return (
    <AppShell>
      <div className="space-y-4">
        <section className="surface-card p-6">
          <h1 className="text-xl font-semibold tracking-tight">API и лимиты</h1>
          <p className="mt-1 text-sm text-[var(--muted)]">
            Статус ключа, текущая нагрузка и ориентиры для интеграции с backend API.
          </p>
        </section>

        <section className="grid gap-4 md:grid-cols-2">
          <div className="surface-card p-5">
            <div className="text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">Использование</div>
            <div className="mt-2 text-2xl font-semibold tracking-tight">
              {loading ? "—" : `${usedThisMonth} / ${MONTH_LIMIT}`}
            </div>
            <div className="mt-3 h-2 rounded-full bg-slate-100">
              <div className="h-2 rounded-full bg-[var(--brand)]" style={{ width: `${usagePct}%` }} />
            </div>
            <div className="mt-2 text-xs text-[var(--muted)]">{loading ? "Загрузка..." : `Заполнено ${usagePct}% месячного лимита`}</div>
          </div>

          <div className="surface-card p-5">
            <div className="text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">API-ключ</div>
            <div className="mt-2 text-base font-semibold">
              {hasKey ? (
                <span className="text-[var(--success)]">Ключ подключен и используется в запросах</span>
              ) : (
                <span className="text-[var(--danger)]">Ключ не задан</span>
              )}
            </div>
            <p className="mt-2 text-xs text-[var(--muted)]">Ключ хранится в localStorage и передаётся в заголовке X-API-Key.</p>
            <div className="mt-3">
              <Link href="/login" className="btn-secondary inline-flex px-3 py-1.5 text-xs font-medium">
                {hasKey ? "Изменить ключ" : "Добавить ключ"}
              </Link>
            </div>
          </div>
        </section>

        <section className="surface-card p-5">
          <h2 className="text-base font-semibold">Параметры интеграции</h2>
          <div className="mt-3 grid gap-3 text-sm md:grid-cols-2">
            <div className="surface-muted p-3">
              <div className="text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">Базовый URL</div>
              <div className="mt-1 break-all font-mono text-xs text-slate-700">{apiBase}</div>
            </div>
            <div className="surface-muted p-3">
              <div className="text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">Основные endpoints</div>
              <div className="mt-1 space-y-1 font-mono text-xs text-slate-700">
                <div>POST /analyze</div>
                <div>GET /analyses</div>
                <div>GET /analyses/{"{id}"}</div>
              </div>
            </div>
          </div>
        </section>
      </div>
    </AppShell>
  );
}
