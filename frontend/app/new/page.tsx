"use client";

import { AppShell } from "@/components/shell/AppShell";
import { useState } from "react";
import Link from "next/link";

type Mode = "pdf" | "text";

export default function NewAnalysisPage() {
  const [mode, setMode] = useState<Mode>("pdf");
  const [cost, setCost] = useState("10000000");
  const [margin, setMargin] = useState("15");
  const [text, setText] = useState("");

  return (
    <AppShell>
      <div className="space-y-4">
        <div className="rounded-2xl border bg-white p-6 shadow-sm">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h1 className="text-xl font-semibold">Новый анализ</h1>
              <p className="mt-1 text-sm text-black/60">
                Загрузите PDF или вставьте текст. Введите себестоимость и маржу — получите вердикт.
              </p>
            </div>
            <Link href="/history" className="text-sm text-black/60 hover:text-black">
              → История
            </Link>
          </div>

          <div className="mt-5 flex gap-2">
            <button
              onClick={() => setMode("pdf")}
              className={[
                "rounded-xl px-3 py-2 text-sm",
                mode === "pdf" ? "bg-black text-white" : "border hover:bg-black/5",
              ].join(" ")}
            >
              PDF
            </button>
            <button
              onClick={() => setMode("text")}
              className={[
                "rounded-xl px-3 py-2 text-sm",
                mode === "text" ? "bg-black text-white" : "border hover:bg-black/5",
              ].join(" ")}
            >
              Текст
            </button>
          </div>

          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <div className="rounded-2xl border p-4">
              {mode === "pdf" ? (
                <div className="rounded-xl border-2 border-dashed p-6 text-center text-sm text-black/60">
                  Dropzone (позже подключим)
                  <div className="mt-1 text-xs text-black/40">
                    Если документ — скан, понадобится OCR
                  </div>
                </div>
              ) : (
                <textarea
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  placeholder="Вставьте текст тендера сюда…"
                  className="h-40 w-full resize-none rounded-xl border p-3 text-sm outline-none focus:ring-2 focus:ring-black/10"
                />
              )}
            </div>

            <div className="rounded-2xl border p-4">
              <label className="block text-xs font-medium text-black/60">Себестоимость (₽)</label>
              <input
                value={cost}
                onChange={(e) => setCost(e.target.value)}
                className="mt-1 w-full rounded-xl border p-3 text-sm outline-none focus:ring-2 focus:ring-black/10"
              />

              <label className="mt-4 block text-xs font-medium text-black/60">Маржа (%)</label>
              <input
                value={margin}
                onChange={(e) => setMargin(e.target.value)}
                className="mt-1 w-full rounded-xl border p-3 text-sm outline-none focus:ring-2 focus:ring-black/10"
              />

              <button
                className="mt-4 w-full rounded-xl bg-black px-4 py-3 text-sm text-white hover:bg-black/90"
                onClick={() => alert("Дальше подключим к /analyze и /analyze/pdf 🙂")}
              >
                Анализировать
              </button>

              <div className="mt-2 text-xs text-black/50">
                Результат сохранится в истории автоматически.
              </div>
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
