"use client";

import { useState } from "react";

function JsonBox({ data }: { data: unknown }) {
  return (
    <pre className="max-h-[420px] overflow-auto rounded-xl border border-[var(--border)] bg-[var(--surface-muted)] p-3 text-xs text-slate-800">
      {JSON.stringify(data, null, 2)}
    </pre>
  );
}

export default function DetailsAccordion({
  extractedData,
  riskReasons,
}: {
  extractedData?: unknown;
  riskReasons?: unknown;
}) {
  const [open, setOpen] = useState(false);

  return (
    <section className="surface-card p-5">
      <button onClick={() => setOpen((v) => !v)} className="flex w-full items-center justify-between" aria-expanded={open}>
        <div className="text-left">
          <h2 className="text-base font-semibold text-slate-900">Технические данные (необязательно)</h2>
          <div className="mt-1 text-xs text-[var(--muted)]">Служебный JSON для проверки модели. Для ежедневной работы можно не открывать.</div>
        </div>
        <span className="btn-secondary px-3 py-1 text-xs font-medium">{open ? "Свернуть" : "Развернуть"}</span>
      </button>

      {open && (
        <div className="mt-4 space-y-4">
          <div>
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">Причины риска (JSON)</div>
            <JsonBox data={riskReasons ?? {}} />
          </div>
          <div>
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">Извлечённые поля (JSON)</div>
            <JsonBox data={extractedData ?? {}} />
          </div>
        </div>
      )}
    </section>
  );
}
