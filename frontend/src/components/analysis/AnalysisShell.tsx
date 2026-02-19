import DecisionHero from "./DecisionHero";
import FinancialSnapshot from "./FinancialSnapshot";
import PrimaryRisks from "./PrimaryRisks";
import FixSuggestions from "./FixSuggestions";
import DangerEvidenceList from "./DangerEvidenceList";
import type { AnalysisViewModel } from "./types";

export default function AnalysisShell({ analysis }: { analysis: AnalysisViewModel }) {
  return (
    <div className="space-y-6">
      <DecisionHero analysis={analysis} />
      <FinancialSnapshot analysis={analysis} />

      <div className="space-y-6">
        <PrimaryRisks items={analysis.primaryRisks} />
        <FixSuggestions items={analysis.fixSuggestions} />
        <DangerEvidenceList items={analysis.dangerPhrases} />
      </div>
    </div>
  );
}
