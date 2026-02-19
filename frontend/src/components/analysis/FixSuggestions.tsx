export default function FixSuggestions({ items }: { items: string[] }) {
  return (
    <section className="surface-card p-5">
      <h2 className="text-base font-semibold text-slate-900">Что улучшить перед участием</h2>
      <p className="mt-1 text-sm text-[var(--muted)]">Шаги, которые снижают риски и делают условия контракта безопаснее.</p>

      <ul className="mt-4 space-y-2">
        {items.map((x, idx) => (
          <li key={idx} className="surface-muted flex items-start gap-2 p-3">
            <span className="mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[var(--brand)] text-xs font-semibold text-white">
              ✓
            </span>
            <span className="text-sm text-slate-800">{x}</span>
          </li>
        ))}
        {!items.length && <li className="text-sm text-[var(--muted)]">Пока нет рекомендаций.</li>}
      </ul>
    </section>
  );
}
