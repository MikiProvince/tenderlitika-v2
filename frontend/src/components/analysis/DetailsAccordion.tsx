"use client";

import { useState } from "react";

function JsonBox({ data }: { data: unknown }) {
  return (
    <pre className="max-h-[420px] overflow-auto rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-800">
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
  // ✅ было true — стало false
  const [open, setOpen] = useState(false);

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between"
      >
        <div className="text-left">
          <h2 className="text-base font-semibold text-slate-900">Детали и исходные данные</h2>
          <div className="mt-1 text-xs text-slate-500">
            Для проверки: причины риска и извлечённые поля (JSON)
          </div>
        </div>
        <span className="text-sm text-slate-600">{open ? "Свернуть" : "Развернуть"}</span>
      </button>

      {open && (
        <div className="mt-4 space-y-4">
          <div>
            <div className="mb-2 text-xs font-semibold text-slate-500">Risk reasons (JSON)</div>
            <JsonBox data={riskReasons ?? {}} />
          </div>
          <div>
            <div className="mb-2 text-xs font-semibold text-slate-500">Extracted data (JSON)</div>
            <JsonBox data={extractedData ?? {}} />
          </div>
        </div>
      )}
    </section>
  );
}
