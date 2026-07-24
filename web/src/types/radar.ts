export type RunStatus = "succeeded";
export type StepStatus = "success" | "error";
export type VerificationStatus = "verified" | "unverified" | "excluded";
export type ImpactStrength = "high" | "medium" | "low" | "unknown";
export type ImpactDirection = "positive" | "negative" | "mixed" | "neutral" | "unknown";
export type ConfidenceLevel = "high" | "medium" | "low" | "unknown";
export type AnalysisStatus = "succeeded" | "failed" | "not_started" | "queued" | "running" | "not_applicable";
export type EventExclusionReason = "" | "pure_stock_price_update";
export type PriorityLevel = "critical" | "verify_first" | "high" | "medium" | "low";
export type AnalysisTier = "pro" | "flash" | "deterministic" | "not_applicable";
export type ImportanceLevel = "high" | "medium" | "low";

export interface RadarStep {
  step_name: string;
  tool_name: string;
  status: StepStatus;
  summary: string;
}

export interface RadarRun {
  id: string;
  event_catalog_id: string;
  status: RunStatus;
  generated_at: string;
  window_start: string;
  window_end: string;
  warnings: string[];
  steps: RadarStep[];
}

export interface RadarSummary {
  total_event_count: number;
  core_event_count: number;
  verified_count: number;
  unverified_count: number;
  excluded_count: number;
  source_count: number;
  alert_count: number;
  research_candidate_count: number;
  critical_event_count: number;
  high_event_count: number;
  verify_first_count: number;
  scoring_version: string;
}

export interface RadarSource {
  source_type: string;
  name: string;
}

export interface ValueChain {
  payer: string;
  receiver: string;
  chain_steps: string[];
  direction: string;
  reasoning: string;
}

export interface RadarCandidate {
  symbol: string;
  name: string;
  market: string;
  event_ids: string[];
  event_titles?: string[];
  impact_type: string;
  impact_strength: ImpactStrength;
  impact_direction: ImpactDirection;
  impact_score: number | null;
  confidence: ConfidenceLevel;
  verification_status: VerificationStatus;
  verification_source: string;
  watchlist_hit: boolean;
  themes: string[];
  reasoning: string;
  evidence: string[];
  risks: string[];
}

export interface FeatureScore {
  value: number;
  reason_codes: string[];
  evidence_refs: string[];
}

export interface StockFeatureBreakdown {
  directness?: FeatureScore;
  exposure?: FeatureScore;
  economic_scale?: FeatureScore;
  duration?: FeatureScore;
  sensitivity?: FeatureScore;
}

export interface ConfidenceFeatureBreakdown {
  source_quality?: FeatureScore;
  corroboration?: FeatureScore;
  identity_verification?: FeatureScore;
  quantitative_completeness?: FeatureScore;
  consistency?: FeatureScore;
}

export interface ScoredRadarCandidate extends Omit<RadarCandidate, "confidence"> {
  positive_magnitude: number;
  negative_magnitude: number;
  confidence: number;
  conflict_score: number;
  priority_level: PriorityLevel;
  analysis_tier: AnalysisTier;
  feature_breakdown: {
    positive?: StockFeatureBreakdown;
    negative?: StockFeatureBreakdown;
    confidence?: ConfidenceFeatureBreakdown;
  };
  reason_codes: string[];
}

export interface RadarResearchCandidate extends RadarCandidate {
  event_titles: string[];
  source_count: number;
  latest_published_at: string;
}

export interface RadarAlert {
  id: string;
  event_id: string;
  event_title: string;
  symbol: string;
  name: string;
  direction: "negative" | "mixed";
  impact_score: number | null;
  confidence: ConfidenceLevel;
  severity: "high" | "medium";
  reasoning: string;
  evidence: string[];
  risks: string[];
  generated_at: string;
}

export interface RadarEvent {
  id: string;
  rank: number;
  title: string;
  latest_published_at: string;
  report_count: number;
  source_count: number;
  sources: RadarSource[];
  source_urls: string[];
  event_type: string;
  themes: string[];
  key_facts: string[];
  overall_direction: ImpactDirection;
  impact_score: number | null;
  confidence: number;
  report_confidence: ConfidenceLevel;
  event_importance: number;
  importance_level: ImportanceLevel;
  analysis_tier: AnalysisTier;
  reason_codes: string[];
  reasoning: string;
  value_chain: ValueChain;
  candidates: RadarCandidate[];
  analysis_status: AnalysisStatus;
  warnings: string[];
}

export interface RadarEventItem {
  headline: string;
  source: string;
  url: string;
  published_at: string;
  source_type: string;
}

export interface RadarEventSummary {
  id: string;
  rank: number;
  title: string;
  latest_published_at: string;
  report_count: number;
  source_count: number;
  sources: RadarSource[];
  source_urls: string[];
  items: RadarEventItem[];
  analysis_status: AnalysisStatus;
  exclusion_reason: EventExclusionReason;
}

export interface EventAnalysisResponse {
  schema_version?: "1.0";
  run_id: string;
  event_id: string;
  status: "queued" | "running" | "succeeded" | "failed";
  generated_at?: string;
  event?: RadarEvent | null;
  steps?: RadarStep[];
  warnings?: string[];
  error?: string;
  markdown?: string;
}

export interface ValidationTask {
  question: string;
  data_needed: string;
  status: "pending" | "done" | "blocked";
  event_ids: string[];
}

export interface CandidateGroups {
  verified: ScoredRadarCandidate[];
  unverified: ScoredRadarCandidate[];
  excluded: ScoredRadarCandidate[];
  watchlist: ScoredRadarCandidate[];
}

export interface RadarSnapshot {
  schema_version: "2.2";
  run: RadarRun;
  summary: RadarSummary;
  events: RadarEvent[];
  all_events: RadarEventSummary[];
  candidate_groups: CandidateGroups;
  alerts: RadarAlert[];
  research_candidates: RadarResearchCandidate[];
  validation_tasks: ValidationTask[];
  disclaimer: string;
}
