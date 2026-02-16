"use client";

import { setApiKey } from "@/lib/storage";
import { useState } from "react";

export default function LoginPage() {
  const [key, setKey] = useState("");

  return (
    <div className="min-h-screen bg-zinc-50 text-zinc-900">
      <div className="mx-auto flex min-h-screen max-w-md items-center px-4">
        <div className="w-full rounded-2xl border bg-white p-6 shadow-sm">
          <div className="text-lg font-semibold">Tenderlitika V2</div>
          <div className="mt-1 text-sm text-black/60">
            Вставь API key (заголовок X-API-Key), чтобы UI мог вызывать бек.
          </div>

          <label className="mt-4 block text-xs font-medium text-black/60">API Key</label>
          <input
            value={key}
            onChange={(e) => setKey(e.target.value)}
            placeholder="tlk_..."
            className="mt-1 w-full rounded-xl border p-3 text-sm outline-none focus:ring-2 focus:ring-black/10"
          />

          <button
            className="mt-4 w-full rounded-xl bg-black px-4 py-3 text-sm text-white hover:bg-black/90"
            onClick={() => {
              setApiKey(key);
              window.location.href = "/dashboard";
            }}
          >
            Сохранить и войти
          </button>

          <div className="mt-3 text-xs text-black/50">
            Ключ можно создать в Swagger через <code>/api-keys</code> (пока MVP).
          </div>
        </div>
      </div>
    </div>
  );
}
