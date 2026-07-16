export type RunStatus = "succeeded";
export type StepStatus = "success" | "error";
export type VerificationStatus = "verified" | "unverified" | "excluded";
export type ImpactStrength = "high" | "medium" | "low" | "unknown";
export type AnalysisStatus = "succeeded" | "failed";

export interface RadarStep {
  step_name: string;
  tool_name: string;
  status: StepStatus;
  summary: string;
}

export interface RadarRun {
  id: string;
  status: RunStatus;
  generated_at: string;
  window_start: string;
  window_end: string;
  warnings: string[];
  steps: RadarStep[];
}

export interface RadarSummary {
  event_count: number;
  verified_count: number;
  unverified_count: number;
  excluded_count: number;
  source_count: number;
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
  verification_status: VerificationStatus;
  verification_source: string;
  watchlist_hit: boolean;
  themes: string[];
  reasoning: string;
  evidence: string[];
  risks: string[];
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
  confidence: string;
  reasoning: string;
  value_chain: ValueChain;
  candidates: RadarCandidate[];
  analysis_status: AnalysisStatus;
  warnings: string[];
}

export interface ValidationTask {
  question: string;
  data_needed: string;
  status: "pending" | "done" | "blocked";
  event_ids: string[];
}

export interface CandidateGroups {
  verified: RadarCandidate[];
  unverified: RadarCandidate[];
  excluded: RadarCandidate[];
  watchlist: RadarCandidate[];
}

export interface RadarSnapshot {
  schema_version: "1.0";
  run: RadarRun;
  summary: RadarSummary;
  events: RadarEvent[];
  candidate_groups: CandidateGroups;
  validation_tasks: ValidationTask[];
  disclaimer: string;
}
