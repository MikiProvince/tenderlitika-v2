import type { Finding } from "./types";

function pill(severity: Finding["severity"]) {
  switch (severity) {
    case "critical":
      return "bg-red-100 text-red-900 border-red-200";
    case "high":
      return "bg-orange-100 text-orange-900 border-orange-200";
    case "medium":
      return "bg-amber-100 text-amber-900 border-amber-200";
    default:
      return "bg-slate-100 text-slate-800 border-slate-200";
  }
}

export default function PrimaryRisks({ items }: { items: Finding[] }) {
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-slate-900">Почему это риск</h2>
        <span className="text-xs text-slate-500">{items.length ? `${items.length} ключевых` : "—"}</span>
      </div>

      <div className="mt-4 space-y-3">
        {items.map((r) => (
          <div key={r.id} className="rounded-xl border border-slate-200 p-4">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="text-sm font-semibold text-slate-900">{r.title}</div>
                {r.impact && <div className="mt-1 text-sm text-slate-700">{r.impact}</div>}
              </div>
              <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold ${pill(r.severity)}`}>
                {r.severity.toUpperCase()}
              </span>
            </div>
            {r.recommendation && (
              <div className="mt-3 rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-700">
                <span className="font-semibold">Что делать:</span> {r.recommendation}
              </div>
            )}
          </div>
        ))}

        {!items.length && <div className="text-sm text-slate-600">Пока нет выделенных ключевых причин.</div>}
      </div>
    </section>
  );
}
