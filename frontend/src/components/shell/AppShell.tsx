"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { clearApiKey, getApiKey } from "@/lib/storage";
import { useEffect, useState } from "react";

function NavItem({ href, label }: { href: string; label: string }) {
  const pathname = usePathname();
  const active = pathname === href || (href !== "/" && pathname.startsWith(href));
  return (
    <Link
      href={href}
      className={[
        "block rounded-xl px-3 py-2 text-sm transition",
        active ? "bg-black text-white" : "hover:bg-black/5 text-black/70",
      ].join(" ")}
    >
      {label}
    </Link>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const [hasKey, setHasKey] = useState(false);

  useEffect(() => {
    setHasKey(!!getApiKey());
  }, []);

  return (
    <div className="min-h-screen bg-zinc-50 text-zinc-900">
      <header className="sticky top-0 z-10 border-b bg-white/80 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
          <Link href="/dashboard" className="font-semibold tracking-tight">
            Tenderlitika <span className="text-black/40">V2</span>
          </Link>

          <div className="flex items-center gap-3">
            <div className="rounded-full bg-black/5 px-3 py-1 text-xs">
              Plan: <span className="font-medium">Free</span>
            </div>

            <div className="rounded-full bg-black/5 px-3 py-1 text-xs">
              API Key:{" "}
              <span className={hasKey ? "font-medium" : "text-black/50"}>
                {hasKey ? "Set" : "Missing"}
              </span>
            </div>

            <button
              className="rounded-full border px-3 py-1 text-xs hover:bg-black/5"
              onClick={() => {
                clearApiKey();
                setHasKey(false);
                window.location.href = "/login";
              }}
              title="Очистить API ключ и выйти"
            >
              Exit
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto grid max-w-6xl grid-cols-12 gap-4 px-4 py-6">
        <aside className="col-span-12 md:col-span-3">
          <div className="rounded-2xl border bg-white p-3 shadow-sm">
            <div className="mb-2 px-2 text-xs font-medium text-black/50">
              Навигация
            </div>
            <nav className="space-y-1">
              <NavItem href="/dashboard" label="Dashboard" />
              <NavItem href="/new" label="Новый анализ" />
              <NavItem href="/history" label="История" />
              <NavItem href="/api" label="API & лимиты" />
            </nav>
          </div>
        </aside>

        <section className="col-span-12 md:col-span-9">{children}</section>
      </main>
    </div>
  );
}
