"use client";

import { AppShell } from "@/components/shell/AppShell";
import { apiFetch } from "@/lib/api";
import Link from "next/link";
import { use, useEffect, useState } from "react";

import AnalysisShell from "@/components/analysis/AnalysisShell";
import type { AnalysisViewModel, Finding, RiskLevel } from "@/components/analysis/types";

type AnalysisDetail = {
  id: number;
  source_type: "pdf" | "text";
  source_name: string | null;
  extracted_data: Record<string, unknown>;
  risk_score: number;
  risk_level: string;
  risk_reasons: any; // может быть json/string[]
  expected_roi_percent: number;
  rough_cash_gap: number | null;
  verdict: string;
  created_at: string;

  input_cost_price: number | null;
  input_margin_percent: number | null;
  safe_cost_price: number | null;
};

// ✅ теперь понимает русские уровни + подстраховывается risk_score
function toRiskLevel(levelText: string, riskScore?: number): RiskLevel {
  const v = (levelText || "").toLowerCase();

  // 1) score надежнее текста
  if (typeof riskScore === "number") {
    if (riskScore >= 10) return "critical";
    if (riskScore >= 9) return "high";
    if (riskScore >= 7) return "medium";
    return "low";
  }

  // 2) EN
  if (v.includes("critical")) return "critical";
  if (v.includes("high")) return "high";
  if (v.includes("medium")) return "medium";
  if (v.includes("low")) return "low";

  // 3) RU
  if (v.includes("крит")) return "critical";
  if (v.includes("высок")) return "high";
  if (v.includes("средн")) return "medium";
  if (v.includes("низк")) return "low";

  return "low";
}

function makeId(prefix: string, i: number) {
  return `${prefix}-${i}-${Math.random().toString(16).slice(2)}`;
}

// Простая эвристика тяжести причины по тексту (быстро, но уже полезно)
function severityFromReasonText(text: string): RiskLevel {
  const t = (text || "").toLowerCase();

  const highSignals = [
    "нет аванс",
    "аванса нет",
    "оплата после полной поставки",
    "после полной поставки",
    "штраф",
    "пеня",
    "обеспечение контракта: 20",
    "обеспечение контракта 20",
    "обеспечение контракта: 30",
    "обеспечение заявки",
    "кассов",
    "замороз",
    "по заявкам",
    "неопределенн",
    "неопределённ",
  ];

  const mediumSignals = [
    "обеспечение контракта",
    "обеспечение заявки",
    "гаранти",
    "срок",
    "растягив",
    "партиями",
    "поэтап",
  ];

  if (highSignals.some((s) => t.includes(s))) return "high";
  if (mediumSignals.some((s) => t.includes(s))) return "medium";
  return "low";
}

function mapAnalysisToVM(a: AnalysisDetail): AnalysisViewModel {
  const extracted = a?.extracted_data ?? {};

  const analysisSeverity = toRiskLevel(a?.risk_level, a?.risk_score);

  // ✅ Danger phrases
  const dangerRaw = extracted?.danger_phrases ?? extracted?.dangerPhrases ?? [];
  const dangerPhrases: Finding[] = Array.isArray(dangerRaw)
    ? dangerRaw.map((d: any, i: number) => {
        const title =
          typeof d === "string" ? d : d?.title || d?.phrase || "Опасная формулировка";

        const sev =
          typeof d === "object" && d?.severity
            ? toRiskLevel(String(d.severity))
            : "medium";

        const quote =
          typeof d === "object"
            ? d?.quote ?? d?.matches?.[0]?.snippet
            : undefined;

        return {
          id: makeId("d", i),
          type: "DANGER_PHRASE",
          severity: sev,
          title,
          impact: typeof d === "object" ? d?.hint || d?.impact : undefined,
          recommendation: typeof d === "object" ? d?.recommendation : undefined,
          evidence: quote ? { quote, page: d?.page, section: d?.section } : undefined,
        };
      })
    : [];

  // ✅ Primary risks (из risk_reasons)
  const reasonsRaw = a?.risk_reasons ?? [];
  const primaryRisks: Finding[] = Array.isArray(reasonsRaw)
    ? reasonsRaw.slice(0, 6).map((r: any, i: number) => {
        const title = typeof r === "string" ? r : r?.title || "Причина риска";
        return {
          id: makeId("r", i),
          type: "PRIMARY_RISK",
          // ✅ разные severity, а не LOW у всего
          severity: severityFromReasonText(title),
          title,
          impact: typeof r === "object" ? r?.impact : undefined,
          recommendation: typeof r === "object" ? r?.recommendation : undefined,
        };
      })
    : [];

  // ✅ Fix suggestions: если бэк не прислал — генерим из extracted_data
  let fixSuggestions: string[] = [];
  const backendFixes =
    extracted?.fix_suggestions ?? extracted?.fixSuggestions ?? null;

  if (Array.isArray(backendFixes) && backendFixes.length) {
    fixSuggestions = backendFixes;
  } else {
    const fixes: string[] = [];

    const advance = Number(extracted?.advance_percent ?? 0);
    const payAfterFull = Boolean(extracted?.payment_after_full_delivery);
    const contractSec = Number(extracted?.contract_security_percent ?? 0);
    const bidSec = Number(extracted?.bid_security_percent ?? 0);
    const deliveryByReq = Boolean(extracted?.delivery_by_customer_requests);

    if (!advance || advance <= 0) {
      fixes.push("Запросить аванс 20–30% или частичную предоплату по этапам/партиям.");
    }
    if (payAfterFull) {
      fixes.push("Разбить оплату по этапам/партиям вместо оплаты после полной поставки.");
    }
    if (contractSec >= 20) {
      fixes.push("Проверить возможность снизить обеспечение контракта до ≤10% или заменить формат (гарантия и т.п.).");
    }
    if (bidSec >= 5) {
      fixes.push("Уточнить условия обеспечения заявки и заложить стоимость заморозки средств/гарантии в цену.");
    }
    if (deliveryByReq) {
      fixes.push("Зафиксировать объём и график поставки: убрать неопределённость “по заявкам” или прописать лимиты/сроки.");
    }

    // Если совсем нет полей — покажем хотя бы 2 универсальных
    if (!fixes.length) {
      fixes.push("Проверить условия оплаты/сроков и оценить потребность в оборотных средствах до участия.");
      fixes.push("Заложить риски штрафов/гарантий/сроков в цену или запросить разъяснения у заказчика.");
    }

    fixSuggestions = fixes;
  }

  return {
    id: a.id,
    createdAt: a.created_at,
    verdict: a.verdict,
    riskScore: a.risk_score,
    riskLevel: analysisSeverity,

    expectedRoiPercent: a.expected_roi_percent,
    roughCashGap: a.rough_cash_gap,
    safeCostPrice: a.safe_cost_price,
    inputCostPrice: a.input_cost_price,
    inputMarginPercent: a.input_margin_percent,

    primaryRisks,
    dangerPhrases,
    fixSuggestions,

    extractedData: extracted,
    riskReasons: a.risk_reasons,

    // можно потом с бэка, сейчас не трогаем
    // confidence: 0.82,
  };
}

export default function AnalysisDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);

  const [data, setData] = useState<AnalysisDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    setError(null);

    apiFetch<AnalysisDetail>(`/analyses/${id}`)
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [id]);

  const vm = data ? mapAnalysisToVM(data) : null;

  return (
    <AppShell>
      <div className="space-y-4">
        {/* Шапка */}
        <div className="rounded-2xl border bg-white p-6 shadow-sm">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h1 className="text-xl font-semibold">Анализ #{id}</h1>
              <p className="mt-1 text-sm text-black/60">
                Вердикт, риски, безопасная цена и доказательства.
              </p>
            </div>

            <div className="flex gap-2">
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
        </div>

        {loading && (
          <div className="rounded-2xl border bg-white p-6 shadow-sm">Загружаем…</div>
        )}

        {error && (
          <div className="rounded-2xl border border-red-200 bg-red-50 p-6 text-red-700 shadow-sm">
            Ошибка: {error}
          </div>
        )}

        {/* Новый UX */}
        {vm && (
          <div className="mx-auto max-w-6xl">
            <AnalysisShell analysis={vm} />
          </div>
        )}
      </div>
    </AppShell>
  );
}
