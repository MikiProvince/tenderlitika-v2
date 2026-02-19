"use client";

import { setApiKey } from "@/lib/storage";
import { useRouter } from "next/navigation";
import { useState } from "react";

export default function LoginPage() {
  const router = useRouter();
  const [key, setKey] = useState("");
  const [error, setError] = useState<string | null>(null);

  const submit = () => {
    if (!key.trim()) {
      setError("Введите API-ключ, чтобы продолжить.");
      return;
    }

    setError(null);
    setApiKey(key);
    router.push("/dashboard");
  };

  return (
    <div className="min-h-screen text-[var(--foreground)]">
      <div className="mx-auto flex min-h-screen max-w-md items-center px-4 py-10">
        <section className="surface-card w-full p-6">
          <div className="text-xl font-semibold tracking-tight">Tenderlitika</div>
          <p className="mt-2 text-sm text-[var(--muted)]">
            Подключите API-ключ, чтобы запускать анализы тендеров, сохранять историю и получать финансовые рекомендации.
          </p>

          <div className="mt-5 space-y-2">
            <label htmlFor="api-key" className="block text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
              API-ключ
            </label>
            <input
              id="api-key"
              value={key}
              onChange={(e) => setKey(e.target.value)}
              placeholder="tlk_..."
              className="w-full rounded-xl border border-[var(--border)] bg-white p-3 text-sm outline-none focus-visible:border-[var(--brand)]"
            />
          </div>

          {error && <div className="mt-3 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}

          <button
            className="btn-primary mt-4 w-full px-4 py-3 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-60"
            onClick={submit}
            disabled={!key.trim()}
          >
            Сохранить и войти
          </button>

          <div className="mt-3 rounded-xl border border-[var(--border)] bg-[var(--surface-muted)] p-3 text-xs text-[var(--muted)]">
            Ключ можно создать через backend endpoint <code>/api-keys</code>. Он хранится локально в браузере и передаётся в заголовке <code>X-API-Key</code>.
          </div>
        </section>
      </div>
    </div>
  );
}
