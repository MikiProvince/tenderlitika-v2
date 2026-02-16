import { AppShell } from "@/components/shell/AppShell";

export default function ApiPage() {
  return (
    <AppShell>
      <div className="space-y-4">
        <div className="rounded-2xl border bg-white p-6 shadow-sm">
          <h1 className="text-xl font-semibold">API & лимиты</h1>
          <p className="mt-1 text-sm text-black/60">
            Здесь будет Usage, создание/отзыв ключей и подсказки для интеграций.
          </p>

          <div className="mt-5 grid gap-4 md:grid-cols-2">
            <div className="rounded-2xl border p-5">
              <div className="text-sm font-medium">Usage</div>
              <div className="mt-2 h-2 w-full rounded-full bg-black/10">
                <div className="h-2 w-1/3 rounded-full bg-black" />
              </div>
              <div className="mt-2 text-xs text-black/60">12 / 30 (заглушка)</div>
            </div>

            <div className="rounded-2xl border p-5">
              <div className="text-sm font-medium">API Keys</div>
              <div className="mt-2 text-xs text-black/60">
                Список ключей и кнопка “Создать ключ” (подключим к API).
              </div>
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
