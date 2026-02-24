"use client";

import { AppShell } from "@/components/shell/AppShell";
import { apiFetch } from "@/lib/api";
import { getLlmProvider } from "@/lib/storage";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

type AnalyzeResponse = {
  analysis_id: number;
  extracted_data: Record<string, unknown>;
  risk_score: number;
  risk_level: string;
  risk_reasons: string[];
  expected_roi_percent: number;
  rough_cash_gap: number | null;
  verdict: string;
};

const LS_COST = "tlk_cost_price";
const LS_MARGIN = "tlk_margin";
const STAGES = ["Извлечение условий", "Расчет рисков и финансов", "Формирование отчета"];
const ACCEPTED_EXTENSIONS = [".pdf", ".doc", ".docx", ".xlsx", ".csv", ".txt"];
const MAX_FILES = 25;
const MAX_FILE_SIZE_MB = 15;
const MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024;

export default function NewAnalysisPage() {
  const router = useRouter();

  const [text, setText] = useState("");
  const [cost, setCost] = useState("1000000");
  const [margin, setMargin] = useState("15");
  const [files, setFiles] = useState<File[]>([]);
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const [loading, setLoading] = useState(false);
  const [stageIndex, setStageIndex] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const hasFiles = files.length > 0;
  const totalBytes = files.reduce((acc, file) => acc + file.size, 0);

  useEffect(() => {
    const savedCost = localStorage.getItem(LS_COST);
    const savedMargin = localStorage.getItem(LS_MARGIN);
    if (savedCost) setCost(savedCost);
    if (savedMargin) setMargin(savedMargin);
  }, []);

  function formatBytes(bytes: number) {
    if (bytes < 1024) return `${bytes} Б`;
    const kb = bytes / 1024;
    if (kb < 1024) return `${kb.toFixed(1)} КБ`;
    const mb = kb / 1024;
    return `${mb.toFixed(1)} МБ`;
  }

  function clearFiles() {
    setFiles([]);
    setError(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  function fileKey(file: File) {
    return `${file.name}:${file.size}:${file.lastModified}`;
  }

  function addFiles(nextFiles: File[]) {
    if (!nextFiles.length) return;

    const merged = [...files, ...nextFiles];
    const unique = new Map<string, File>();
    for (const file of merged) {
      unique.set(fileKey(file), file);
    }
    const uniqueFiles = Array.from(unique.values());

    if (uniqueFiles.length > MAX_FILES) {
      setError(`Можно загрузить не больше ${MAX_FILES} файлов.`);
      if (fileInputRef.current) fileInputRef.current.value = "";
      return;
    }

    for (const file of uniqueFiles) {
      const name = file.name.toLowerCase();
      const dotIndex = name.lastIndexOf(".");
      const ext = dotIndex >= 0 ? name.slice(dotIndex) : "";

      if (!ACCEPTED_EXTENSIONS.includes(ext)) {
        setError(`Формат ${ext || "без расширения"} не поддерживается. Разрешены PDF, DOC, DOCX, XLSX, CSV, TXT.`);
        if (fileInputRef.current) fileInputRef.current.value = "";
        return;
      }

      if (file.size > MAX_FILE_SIZE_BYTES) {
        setError(`Файл ${file.name} больше ${MAX_FILE_SIZE_MB} МБ. Загрузите меньший документ.`);
        if (fileInputRef.current) fileInputRef.current.value = "";
        return;
      }
    }

    setError(null);
    setFiles(uniqueFiles);
  }

  function handleFileSelect(list: FileList | File[] | null) {
    if (!list) return;
    const nextFiles = Array.isArray(list) ? list : Array.from(list);
    addFiles(nextFiles);
  }

  function removeFileAt(index: number) {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  }

  function validate() {
    const parsedCost = Number(cost);
    const parsedMargin = Number(margin);

    if (!files.length && !text.trim()) return "Загрузите документы или вставьте текст закупки перед запуском анализа.";
    if (!Number.isFinite(parsedCost) || parsedCost <= 0) return "Себестоимость должна быть больше 0.";
    if (!Number.isFinite(parsedMargin) || parsedMargin < 0 || parsedMargin > 100) return "Маржа должна быть в диапазоне 0-100%.";

    return null;
  }

  async function onAnalyze() {
    const validationError = validate();
    if (validationError) {
      setError(validationError);
      return;
    }

    setError(null);
    setLoading(true);
    setStageIndex(0);

    try {
      localStorage.setItem(LS_COST, cost);
      localStorage.setItem(LS_MARGIN, margin);

      setStageIndex(1);
      let res: AnalyzeResponse;

      if (files.length) {
        const formData = new FormData();
        files.forEach((file) => formData.append("files", file));
        formData.append("cost_price", String(Number(cost)));
        formData.append("planned_margin_percent", String(Number(margin)));
        formData.append("llm_provider", getLlmProvider());

        res = await apiFetch<AnalyzeResponse>("/analyze/batch", {
          method: "POST",
          body: formData,
        });
      } else {
        const payload = {
          text: text.trim(),
          cost_price: Number(cost),
          planned_margin_percent: Number(margin),
          llm_provider: getLlmProvider(),
        };

        res = await apiFetch<AnalyzeResponse>("/analyze", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
      }

      setStageIndex(2);
      router.push(`/analysis/${res.analysis_id}`);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);

      if (msg.includes("Missing X-API-Key") || msg.includes("Invalid API key") || msg.includes("401")) {
        setError("API-ключ не задан или неверный. Перейдите в раздел входа и обновите ключ.");
      } else if (msg.includes("Quota exceeded") || msg.includes("429")) {
        setError("Лимит анализов исчерпан. Дождитесь сброса лимита или обновите тариф.");
      } else {
        setError(msg);
      }
    } finally {
      setLoading(false);
      setStageIndex(null);
    }
  }

  return (
    <AppShell>
      <div className="space-y-4">
        <section className="surface-card p-6">
          <h1 className="text-xl font-semibold tracking-tight">Новый анализ</h1>
          <p className="mt-1 text-sm text-[var(--muted)]">
            Вставьте текст закупки и финансовые параметры. Сервис рассчитает риск, ROI и ориентир безопасной цены.
          </p>
        </section>

        <section className="grid gap-4 md:grid-cols-2">
          <div className="space-y-4">
            <div className="surface-card p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">Документ закупки</div>
                  <p className="mt-1 text-xs text-[var(--muted)]">
                    PDF, DOC, DOCX, XLSX, CSV, TXT. До {MAX_FILES} файлов, {MAX_FILE_SIZE_MB} МБ каждый.
                  </p>
                </div>
                {hasFiles && (
                  <button type="button" className="btn-secondary px-3 py-1 text-xs" onClick={clearFiles}>
                    Очистить
                  </button>
                )}
              </div>

              <label
                htmlFor="tender-file"
                className={[
                  "mt-4 flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed px-4 py-6 text-center",
                  dragActive
                    ? "border-[var(--brand)] bg-blue-50 shadow-sm"
                    : "border-[var(--border)] bg-[var(--surface-muted)]",
                ].join(" ")}
                onDragEnter={(e) => {
                  e.preventDefault();
                  setDragActive(true);
                }}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragActive(true);
                }}
                onDragLeave={(e) => {
                  e.preventDefault();
                  setDragActive(false);
                }}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragActive(false);
                  handleFileSelect(e.dataTransfer.files);
                }}
              >
                <input
                  ref={fileInputRef}
                  id="tender-file"
                  type="file"
                  multiple
                  accept={ACCEPTED_EXTENSIONS.join(",")}
                  className="sr-only"
                  onChange={(e) => handleFileSelect(e.target.files)}
                />
                <div className="flex h-12 w-12 items-center justify-center rounded-full border border-white bg-white shadow-sm">
                  <svg
                    aria-hidden
                    viewBox="0 0 24 24"
                    className="h-5 w-5 text-[var(--brand)]"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.6"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 16V8m0 0l-3 3m3-3l3 3" />
                    <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2" />
                  </svg>
                </div>
                <div className="mt-3 text-sm font-semibold">Перетащите документы сюда</div>
                <div className="mt-1 text-xs text-[var(--muted)]">или нажмите, чтобы выбрать файлы</div>
                <span className="btn-secondary mt-3 px-3 py-1 text-xs">Выбрать файлы</span>
              </label>

              {hasFiles && (
                <div className="mt-3 space-y-2">
                  {files.map((file, idx) => (
                    <div
                      key={fileKey(file)}
                      className="flex items-center justify-between gap-3 rounded-xl border border-[var(--border)] bg-[var(--surface-muted)] p-3"
                    >
                      <div className="min-w-0">
                        <div className="truncate text-sm font-medium">{file.name}</div>
                        <div className="text-xs text-[var(--muted)]">
                          {formatBytes(file.size)}{file.type ? ` • ${file.type}` : ""}
                        </div>
                      </div>
                      <button type="button" className="btn-secondary px-3 py-1 text-xs" onClick={() => removeFileAt(idx)}>
                        Удалить
                      </button>
                    </div>
                  ))}
                  <div className="text-xs text-[var(--muted)]">Выбрано: {files.length} • {formatBytes(totalBytes)}</div>
                </div>
              )}

              <div className="mt-3 text-xs text-[var(--muted)]">
                Если файлы выбраны, анализируем пакет и игнорируем текст ниже.
              </div>
            </div>

            <div className="surface-card p-4">
              <label htmlFor="tender-text" className="block text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
                Текст закупки
              </label>
              <textarea
                id="tender-text"
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="Вставьте сюда текст документа или ключевые разделы закупки..."
                disabled={hasFiles}
                className={[
                  "mt-2 h-72 w-full resize-none rounded-xl border border-[var(--border)] p-3 text-sm outline-none",
                  hasFiles
                    ? "cursor-not-allowed bg-slate-50 text-[var(--muted)]"
                    : "bg-white focus-visible:border-[var(--brand)]",
                ].join(" ")}
              />
              <div className="mt-2 text-xs text-[var(--muted)]">
                Лучше всего работают фрагменты с оплатой, сроками поставки, обеспечением и штрафами.
              </div>
              {hasFiles && (
                <div className="mt-2 text-xs text-[var(--muted)]">Файлы выбраны - поле можно оставить пустым.</div>
              )}
            </div>
          </div>

          <div className="space-y-4">
            <div className="surface-card p-4">
              <label htmlFor="cost" className="block text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
                Себестоимость (₽)
              </label>
              <input
                id="cost"
                value={cost}
                onChange={(e) => setCost(e.target.value)}
                inputMode="decimal"
                className="mt-2 w-full rounded-xl border border-[var(--border)] bg-white p-3 text-sm outline-none focus-visible:border-[var(--brand)]"
              />

              <label htmlFor="margin" className="mt-4 block text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
                Плановая маржа (%)
              </label>
              <input
                id="margin"
                value={margin}
                onChange={(e) => setMargin(e.target.value)}
                inputMode="decimal"
                className="mt-2 w-full rounded-xl border border-[var(--border)] bg-white p-3 text-sm outline-none focus-visible:border-[var(--brand)]"
              />

              {error && <div className="mt-4 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}

              <button
                disabled={loading}
                className="btn-primary mt-4 w-full px-4 py-3 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-60"
                onClick={onAnalyze}
              >
                {loading ? "Выполняем анализ..." : "Запустить анализ"}
              </button>

              <div className="mt-2 text-xs text-[var(--muted)]">Результат автоматически сохраняется в истории.</div>
            </div>

            <div className="surface-card p-4" aria-live="polite">
              <div className="text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">Прогресс</div>
              <div className="mt-3 space-y-2">
                {STAGES.map((stage, idx) => {
                  const isDone = stageIndex !== null && idx < stageIndex;
                  const isCurrent = stageIndex === idx;

                  return (
                    <div key={stage} className="flex items-center gap-2 text-sm">
                      <span
                        className={[
                          "inline-flex h-6 w-6 items-center justify-center rounded-full border text-xs font-semibold",
                          isDone ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "",
                          isCurrent ? "border-[var(--brand)] bg-blue-50 text-[var(--brand)]" : "",
                          !isDone && !isCurrent ? "border-[var(--border)] bg-white text-[var(--muted)]" : "",
                        ].join(" ")}
                      >
                        {isDone ? "✓" : idx + 1}
                      </span>
                      <span className={isCurrent ? "font-medium text-slate-900" : "text-[var(--muted)]"}>{stage}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </section>
      </div>
    </AppShell>
  );
}
