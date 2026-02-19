import DecisionHero from "./DecisionHero";
import FinancialSnapshot from "./FinancialSnapshot";
import PrimaryRisks from "./PrimaryRisks";
import FixSuggestions from "./FixSuggestions";
import DangerEvidenceList from "./DangerEvidenceList";
import DetailsAccordion from "./DetailsAccordion";
import type { AnalysisViewModel } from "./types";

export default function AnalysisShell({ analysis }: { analysis: AnalysisViewModel }) {
  return (
    <div className="space-y-6">
      <DecisionHero analysis={analysis} />
      <FinancialSnapshot analysis={analysis} />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        <div className="lg:col-span-7 space-y-6">
          <PrimaryRisks items={analysis.primaryRisks} />
          <FixSuggestions items={analysis.fixSuggestions} />
          <DangerEvidenceList items={analysis.dangerPhrases} />
        </div>

        <div className="lg:col-span-5 space-y-6">
          <DetailsAccordion extractedData={analysis.extractedData} riskReasons={analysis.riskReasons} />
        </div>
      </div>
    </div>
  );
}
