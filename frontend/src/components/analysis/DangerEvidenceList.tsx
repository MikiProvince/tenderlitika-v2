import type { Finding } from "./types";

export default function DangerEvidenceList({ items }: { items: Finding[] }) {
  return (
    <section className="surface-card p-5">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-slate-900">Опасные формулировки</h2>
        <span className="text-xs text-[var(--muted)]">{items.length ? `${items.length} находок` : "—"}</span>
      </div>

      <div className="mt-4 space-y-3">
        {items.map((f) => (
          <div key={f.id} className="surface-muted p-4">
            <div className="text-sm font-semibold text-slate-900">{f.title}</div>
            {f.impact && <div className="mt-1 text-sm text-slate-700">{f.impact}</div>}

            {f.evidence?.quote && (
              <div className="mt-3 rounded-lg border border-slate-200 bg-white p-3 text-sm text-slate-700">
                <div className="text-xs font-semibold text-[var(--muted)]">
                  Доказательство{typeof f.evidence.page === "number" ? ` • стр. ${f.evidence.page}` : ""}
                </div>
                <div className="mt-1 whitespace-pre-wrap leading-relaxed">“{f.evidence.quote}”</div>
              </div>
            )}

            {f.recommendation && (
              <div className="mt-3 text-sm text-slate-700">
                <span className="font-semibold">Рекомендация:</span> {f.recommendation}
              </div>
            )}
          </div>
        ))}

        {!items.length && <div className="text-sm text-[var(--muted)]">Опасные формулировки не обнаружены.</div>}
      </div>
    </section>
  );
}
