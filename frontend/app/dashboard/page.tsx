import { AppShell } from "@/components/shell/AppShell";
import Link from "next/link";

export default function DashboardPage() {
  return (
    <AppShell>
      <div className="space-y-4">
        <div className="rounded-2xl border bg-white p-6 shadow-sm">
          <h1 className="text-xl font-semibold">Dashboard</h1>
          <p className="mt-1 text-sm text-black/60">
            Быстрый старт: загрузите PDF или вставьте текст — получите вердикт и причины.
          </p>

          <div className="mt-4 flex gap-2">
            <Link
              href="/new"
              className="rounded-xl bg-black px-4 py-2 text-sm text-white hover:bg-black/90"
            >
              Новый анализ
            </Link>
            <Link
              href="/history"
              className="rounded-xl border px-4 py-2 text-sm hover:bg-black/5"
            >
              История
            </Link>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <div className="rounded-2xl border bg-white p-5 shadow-sm">
            <div className="text-sm font-medium">Лимит</div>
            <div className="mt-2 h-2 w-full rounded-full bg-black/10">
              <div className="h-2 w-1/3 rounded-full bg-black" />
            </div>
            <div className="mt-2 text-xs text-black/60">12 / 30 анализов (заглушка UI)</div>
          </div>

          <div className="rounded-2xl border bg-white p-5 shadow-sm">
            <div className="text-sm font-medium">Последний результат</div>
            <div className="mt-2 text-xs text-black/60">
              Здесь будет карточка последнего анализа (после подключения API).
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
