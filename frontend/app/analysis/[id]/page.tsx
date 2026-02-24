"use client";

import { AppShell } from "@/components/shell/AppShell";
import AnalysisShell from "@/components/analysis/AnalysisShell";
import type { AnalysisViewModel, Finding, RiskLevel } from "@/components/analysis/types";
import { apiFetch } from "@/lib/api";
import Link from "next/link";
import { use, useEffect, useState } from "react";

type JsonValue = string | number | boolean | null | JsonObject | JsonValue[];
type JsonObject = { [key: string]: JsonValue };

type RiskReasonObject = {
  title?: string;
  impact?: string;
  recommendation?: string;
};

type DangerPhraseObject = {
  title?: string;
  phrase?: string;
  severity?: string;
  quote?: string;
  matches?: Array<{ snippet?: string }>;
  hint?: string;
  impact?: string;
  recommendation?: string;
  page?: number;
  section?: string;
};

type AnalysisDetail = {
  id: number;
  source_type: "pdf" | "text" | "doc" | "docx" | "batch";
  source_name: string | null;
  extracted_data: Record<string, unknown>;
  risk_score: number;
  risk_level: string;
  risk_reasons: unknown;
  expected_roi_percent: number;
  rough_cash_gap: number | null;
  verdict: string;
  created_at: string;
  input_cost_price: number | null;
  input_margin_percent: number | null;
  safe_cost_price: number | null;
};

type RequestState = {
  id: string;
  data: AnalysisDetail | null;
  error: string | null;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function asJsonObject(value: unknown): JsonObject {
  return isRecord(value) ? (value as JsonObject) : {};
}

function asNumber(value: unknown, fallback = 0): number {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return fallback;
}

function toRiskLevel(levelText: string, riskScore?: number): RiskLevel {
  const v = (levelText || "").toLowerCase();

  if (typeof riskScore === "number") {
    if (riskScore >= 10) return "critical";
    if (riskScore >= 9) return "high";
    if (riskScore >= 7) return "medium";
    return "low";
  }

  if (v.includes("critical")) return "critical";
  if (v.includes("high")) return "high";
  if (v.includes("medium")) return "medium";
  if (v.includes("low")) return "low";

  if (v.includes("крит")) return "critical";
  if (v.includes("высок")) return "high";
  if (v.includes("средн")) return "medium";
  if (v.includes("низк")) return "low";

  return "low";
}

function makeId(prefix: string, i: number, title: string): string {
  const slug = title.toLowerCase().replace(/[^a-zа-я0-9]+/gi, "-").replace(/^-+|-+$/g, "");
  return `${prefix}-${i}-${slug || "item"}`;
}

function severityFromReasonText(text: string): RiskLevel {
  const t = text.toLowerCase();

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

  if (highSignals.some((signal) => t.includes(signal))) return "high";
  if (mediumSignals.some((signal) => t.includes(signal))) return "medium";
  return "low";
}

function mapAnalysisToVM(a: AnalysisDetail): AnalysisViewModel {
  const extracted = asJsonObject(a.extracted_data);
  const analysisSeverity = toRiskLevel(a.risk_level, a.risk_score);

  const dangerRaw = extracted["danger_phrases"] ?? extracted["dangerPhrases"];
  const dangerItems = Array.isArray(dangerRaw) ? dangerRaw : [];

  const dangerPhrases: Finding[] = dangerItems.map((item, i) => {
    const danger: DangerPhraseObject | null = isRecord(item) ? (item as DangerPhraseObject) : null;
    const title = typeof item === "string" ? item : danger?.title || danger?.phrase || "Опасная формулировка";
    const severity = danger?.severity ? toRiskLevel(String(danger.severity)) : "medium";
    const firstMatch = Array.isArray(danger?.matches) ? danger?.matches[0] : undefined;
    const quote = danger?.quote ?? firstMatch?.snippet;

    return {
      id: makeId("d", i, title),
      type: "DANGER_PHRASE",
      severity,
      title,
      impact: danger?.hint || danger?.impact,
      recommendation: danger?.recommendation,
      evidence: quote
        ? {
            quote,
            page: typeof danger?.page === "number" ? danger.page : undefined,
            section: typeof danger?.section === "string" ? danger.section : undefined,
          }
        : undefined,
    };
  });

  const reasonsRaw = Array.isArray(a.risk_reasons) ? a.risk_reasons : [];

  const primaryRisks: Finding[] = reasonsRaw.slice(0, 6).map((item, i) => {
    const reason: RiskReasonObject | null = isRecord(item) ? (item as RiskReasonObject) : null;
    const title = typeof item === "string" ? item : reason?.title || "Причина риска";

    return {
      id: makeId("r", i, title),
      type: "PRIMARY_RISK",
      severity: severityFromReasonText(title),
      title,
      impact: reason?.impact,
      recommendation: reason?.recommendation,
    };
  });

  let fixSuggestions: string[] = [];
  const backendFixes = extracted["fix_suggestions"] ?? extracted["fixSuggestions"];

  if (Array.isArray(backendFixes) && backendFixes.every((entry) => typeof entry === "string") && backendFixes.length) {
    fixSuggestions = backendFixes;
  } else {
    const fixes: string[] = [];

    const advance = asNumber(extracted["advance_percent"]);
    const payAfterFull = Boolean(extracted["payment_after_full_delivery"]);
    const contractSec = asNumber(extracted["contract_security_percent"]);
    const bidSec = asNumber(extracted["bid_security_percent"]);
    const deliveryByReq = Boolean(extracted["delivery_by_customer_requests"]);

    if (!advance || advance <= 0) {
      fixes.push("Запросить аванс 20–30% или частичную предоплату по этапам/партиям.");
    }
    if (payAfterFull) {
      fixes.push("Разбить оплату по этапам/партиям вместо оплаты после полной поставки.");
    }
    if (contractSec >= 20) {
      fixes.push("Проверить возможность снизить обеспечение контракта до <=10% или заменить формат (гарантия и т.п.).");
    }
    if (bidSec >= 5) {
      fixes.push("Уточнить условия обеспечения заявки и заложить стоимость заморозки средств/гарантии в цену.");
    }
    if (deliveryByReq) {
      fixes.push("Зафиксировать объём и график поставки: убрать неопределённость 'по заявкам' или прописать лимиты/сроки.");
    }

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
  };
}

export default function AnalysisDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);

  const [state, setState] = useState<RequestState>({
    id: "",
    data: null,
    error: null,
  });

  useEffect(() => {
    let cancelled = false;

    apiFetch<AnalysisDetail>(`/analyses/${id}`)
      .then((nextData) => {
        if (cancelled) return;
        setState({ id, data: nextData, error: null });
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setState({ id, data: null, error: String(e instanceof Error ? e.message : e) });
      });

    return () => {
      cancelled = true;
    };
  }, [id]);

  const loading = state.id !== id;
  const error = loading ? null : state.error;
  const data = loading ? null : state.data;
  const vm = data ? mapAnalysisToVM(data) : null;

  return (
    <AppShell>
      <div className="space-y-4">
        <section className="surface-card p-6">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h1 className="text-xl font-semibold tracking-tight">Анализ #{id}</h1>
              <p className="mt-1 text-sm text-[var(--muted)]">Вердикт, риски, безопасная цена и доказательства по контракту.</p>
            </div>

            <div className="flex gap-2">
              <Link href="/new" className="btn-primary px-4 py-2 text-sm font-medium">
                Новый анализ
              </Link>
              <Link href="/history" className="btn-secondary px-4 py-2 text-sm font-medium">
                История
              </Link>
            </div>
          </div>
        </section>

        {loading && (
          <section className="surface-card p-6">
            <div className="text-sm text-[var(--muted)]">Загружаем данные анализа...</div>
          </section>
        )}

        {error && (
          <section className="surface-card border-red-200 bg-red-50 p-6 text-red-700">
            Ошибка: {error}
          </section>
        )}

        {vm && (
          <div className="mx-auto max-w-6xl">
            <AnalysisShell analysis={vm} />
          </div>
        )}
      </div>
    </AppShell>
  );
}
