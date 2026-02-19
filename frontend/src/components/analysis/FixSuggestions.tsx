export default function FixSuggestions({ items }: { items: string[] }) {
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5">
      <h2 className="text-base font-semibold text-slate-900">Что исправит ситуацию</h2>
      <p className="mt-1 text-sm text-slate-600">Предложения, которые делают контракт ближе к “безопасному”.</p>

      <ul className="mt-4 space-y-2">
        {items.map((x, idx) => (
          <li key={idx} className="flex items-start gap-2 rounded-xl border border-slate-200 p-3">
            <span className="mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-slate-900 text-xs font-semibold text-white">
              ✓
            </span>
            <span className="text-sm text-slate-800">{x}</span>
          </li>
        ))}
        {!items.length && <li className="text-sm text-slate-600">Пока нет рекомендаций.</li>}
      </ul>
    </section>
  );
}
