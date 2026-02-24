"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { clearApiKey, getApiKey, getLlmProvider, setLlmProvider, subscribeToApiKey, subscribeToLlmProvider } from "@/lib/storage";
import { useSyncExternalStore } from "react";

function NavItem({ href, label }: { href: string; label: string }) {
  const pathname = usePathname();
  const active = pathname === href || (href !== "/" && pathname.startsWith(href));

  return (
    <Link
      href={href}
      className={[
        "block rounded-xl px-3 py-2 text-sm font-medium transition",
        active
          ? "bg-[var(--brand)] text-white shadow-sm"
          : "text-[var(--muted)] hover:bg-[var(--surface-muted)] hover:text-[var(--foreground)]",
      ].join(" ")}
    >
      {label}
    </Link>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const hasKey = useSyncExternalStore(subscribeToApiKey, () => !!getApiKey(), () => false);
  const provider = useSyncExternalStore(subscribeToLlmProvider, getLlmProvider, () => "auto");

  return (
    <div className="min-h-screen text-[var(--foreground)]">
      <header className="sticky top-0 z-20 border-b border-[var(--border)] bg-white/80 backdrop-blur">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <Link href="/dashboard" className="min-w-0">
            <div className="truncate text-base font-semibold tracking-tight">Tenderlitika</div>
            <div className="text-xs text-[var(--muted)]">Оценка тендерных рисков</div>
          </Link>

          <div className="flex items-center gap-2">
            <div className="status-chip px-3 py-1 text-xs text-[var(--muted)]">
              Тариф: <span className="font-semibold text-[var(--foreground)]">Free</span>
            </div>

            <label className="flex items-center gap-2 rounded-full border border-[var(--border)] bg-white px-3 py-1 text-xs text-[var(--muted)]">
              <span>Провайдер</span>
              <select
                value={provider}
                onChange={(e) => setLlmProvider(e.target.value)}
                className="bg-transparent text-xs font-semibold text-[var(--foreground)] outline-none"
                aria-label="Выбор провайдера LLM"
              >
                <option value="auto">Авто</option>
                <option value="gemini">Gemini</option>
                <option value="gigachat">GigaChat</option>
              </select>
            </label>

            <div className="status-chip px-3 py-1 text-xs text-[var(--muted)]">
              API-ключ:{" "}
              <span className={hasKey ? "font-semibold text-[var(--success)]" : "font-semibold text-[var(--danger)]"}>
                {hasKey ? "подключен" : "не задан"}
              </span>
            </div>

            <button
              className="btn-secondary rounded-full px-3 py-1 text-xs"
              onClick={() => {
                clearApiKey();
                window.location.href = "/login";
              }}
              title="Очистить API ключ и выйти"
            >
              Выйти
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto grid max-w-6xl grid-cols-12 gap-4 px-4 py-6">
        <aside className="col-span-12 md:col-span-3">
          <div className="surface-card p-3">
            <div className="mb-2 px-2 text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">Навигация</div>
            <nav className="space-y-1">
              <NavItem href="/dashboard" label="Обзор" />
              <NavItem href="/new" label="Новый анализ" />
              <NavItem href="/history" label="История" />
              <NavItem href="/api" label="API и лимиты" />
            </nav>
          </div>
        </aside>

        <section className="page-enter col-span-12 md:col-span-9">{children}</section>
      </main>
    </div>
  );
}
