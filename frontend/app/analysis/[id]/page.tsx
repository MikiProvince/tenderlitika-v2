import { AppShell } from "@/components/shell/AppShell";

export default function AnalysisDetailPage({ params }: { params: { id: string } }) {
  return (
    <AppShell>
      <div className="space-y-4">
        <div className="rounded-2xl border bg-white p-6 shadow-sm">
          <h1 className="text-xl font-semibold">Анализ #{params.id}</h1>
          <p className="mt-1 text-sm text-black/60">
            Здесь будет экран результата: вердикт, метрики, причины, детали.
          </p>

          <div className="mt-4 grid gap-3 md:grid-cols-3">
            <div className="rounded-xl border p-4">
              <div className="text-xs text-black/50">Risk Score</div>
              <div className="mt-1 text-lg font-semibold">—</div>
            </div>
            <div className="rounded-xl border p-4">
              <div className="text-xs text-black/50">ROI</div>
              <div className="mt-1 text-lg font-semibold">—</div>
            </div>
            <div className="rounded-xl border p-4">
              <div className="text-xs text-black/50">Cash gap</div>
              <div className="mt-1 text-lg font-semibold">—</div>
            </div>
          </div>

          <div className="mt-4 rounded-xl border p-4 text-sm text-black/60">
            Reasons + Accordion details (подключим после API).
          </div>
        </div>
      </div>
    </AppShell>
  );
}
