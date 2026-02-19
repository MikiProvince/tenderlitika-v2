export type RiskLevel = "low" | "medium" | "high" | "critical";

export type FindingType = "PRIMARY_RISK" | "DANGER_PHRASE" | "COST_DRIVER" | "GAP";

export type Evidence = {
  quote: string;
  page?: number;
  section?: string;
};

export type Finding = {
  id: string;
  type: FindingType;
  category?: string;
  severity: RiskLevel;
  title: string;
  impact?: string;
  recommendation?: string;
  evidence?: Evidence;
};

export type AnalysisViewModel = {
  id: number;
  createdAt: string;
  verdict: string;
  riskScore: number;
  riskLevel: RiskLevel;

  expectedRoiPercent?: number | null;
  safeCostPrice?: number | null;
  inputCostPrice?: number | null;
  inputMarginPercent?: number | null;
  roughCashGap?: number | null;

  primaryRisks: Finding[];
  dangerPhrases: Finding[];
  fixSuggestions: string[];

  extractedData?: unknown;
  riskReasons?: unknown;

  confidence?: number;
};
