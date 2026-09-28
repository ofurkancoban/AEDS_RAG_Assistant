// Shapes here mirror the real FastAPI backend's response models
// (see api/routes_chat.py and api/routes_admin.py) - there is no client-held
// document/chunk/embedding state in this app; the backend is the only source
// of truth.

export interface ChatSource {
  source_id: string;
  page: number | null;
  url: string | null;
  // ISO date this source's content stopped being current, or null while
  // still valid (see db/freshness.py).
  expired_since: string | null;
}

export interface RetrievalDiagnostic {
  source_id: string;
  snippet: string;
  hybrid_score: number | null;
  rerank_score: number | null;
  // ISO date this chunk's source stopped being current, or null while still
  // valid (see db/freshness.py).
  expired_since: string | null;
}

export interface ChatQueryResult {
  id: string;
  query: string;
  answer: string;
  sources: ChatSource[];
  retrieval: RetrievalDiagnostic[];
  nodeLatencies: Record<string, number>;
  autoFlaggedContribution: string | null;
  timestamp: number;
  // Ties a thumbs rating back to the logged query row; null when the backend
  // did not log the turn.
  queryLogId: number | null;
  cached: boolean;
  /** Wall-clock milliseconds from pressing send to the answer being complete.
      Measured in the browser rather than taken from node_latencies, because
      that is what the person waited through: it includes the queue behind
      other askers and the network, and it is present for a cache hit, where
      the server reports no node timings at all. */
  elapsedMs: number;
  // True when this answer states an application deadline has already
  // passed. Such answers bypass document retrieval entirely (see
  // graph/build_graph.py's _has_passed_deadline), so they have no `sources`
  // for the per-passage "Outdated since ..." badge to attach to.
  hasExpiredDeadline: boolean;
}

export interface UserSession {
  token: string;
  email: string;
  role: 'admin' | 'user';
}

export type SubmissionStatus = 'pending' | 'approved' | 'rejected' | 'revoked';

export interface PendingSubmission {
  id: number;
  submission_type: 'new_info' | 'correction';
  /** 'revoked' = was approved and vectorized, then pulled back out of the corpus. */
  status: SubmissionStatus;
  source_id: string;
  content: string;
  related_chunk_id: string | null;
  created_at: string;
  /** Patterns suggesting the text is addressed to the model, not to a reader.
      Advisory only - nothing is auto-rejected on the strength of it. */
  injection_markers: string[];
}

export interface IngestedDocumentInfo {
  filename: string;
  chunk_count: number;
  ingested_at: string;
  valid_until: string | null;
  expired: boolean;
}

/** A source URL scripts/source_refresh.py found changed since it last
    checked - detect-only, the curated file is untouched until an admin
    reviews the diff and re-curates it by hand. */
export interface SourceChange {
  filename: string;
  url: string | null;
  last_checked_at: string | null;
  last_changed_at: string;
  diff: string;
}

export interface QuestionCount {
  question: string;
  count: number;
}

export interface UsageAnalytics {
  total_queries: number;
  unanswered_queries: number;
  cache_hit_rate: number;
  thumbs_up: number;
  thumbs_down: number;
  avg_latency_ms: number;
  top_questions: QuestionCount[];
  /** Questions the corpus could not answer - the content-gap backlog. */
  content_gaps: QuestionCount[];
  thumbs_down_questions: string[];
}

export interface ConfigField<T = unknown> {
  value: T;
  read_only: boolean;
  note?: string | null;
}

export interface AdminConfig {
  /** The model actually answering, whichever provider is active. */
  chat_model: ConfigField<string>;
  /** The built-in grounding prompt, used whenever the override is empty. */
  default_system_prompt: ConfigField<string>;
  /** Live-editable: which chat/classifier provider is active - takes effect
      on the next turn, no restart. */
  llm_provider: ConfigField<string>;
  gemini_model: ConfigField<string>;
  openrouter_model: ConfigField<string | null>;
  openrouter_fallback_model: ConfigField<string | null>;
  retrieval_top_k: ConfigField<number>;
  rerank_top_k: ConfigField<number>;
  conversation_history_window: ConfigField<number>;
  system_prompt_override: ConfigField<string | null>;
  embedding_provider: ConfigField<string>;
  embedding_model: ConfigField<string>;
  reranker_model: ConfigField<string>;
  chunk_size: ConfigField<number>;
  chunk_overlap: ConfigField<number>;
}

export interface AdminStats {
  total_chunks: number;
  total_sources: number;
  embedding_dimension: number;
  embedding_model: string;
  reranker_model: string;
  llm_model: string;
  llm_provider: string;
  pending_submissions: number;
  pending_answers: number;
  expired_documents: number;
  llm_calls_today: number;
  llm_daily_budget: number;
  pending_source_changes: number;
}

export type AnswerStatus = 'pending' | 'approved' | 'rejected';

/** A question a student asked, with the answer given for it, awaiting review.
    Only approved entries are ever replayed to future askers. */
export interface ReviewedAnswer {
  id: number;
  question: string;
  answer: string;
  /** What the model produced, when an admin has since rewritten `answer`. */
  original_answer: string | null;
  status: AnswerStatus;
  edited: boolean;
  sources: string[];
  hit_count: number;
  admin_note: string | null;
  created_at: string;
  reviewed_at: string | null;
  /** Computed over the question and answer together. */
  injection_markers: string[];
  /** Which frontend this came in through - the browser's Origin header
      (the main site vs. a third-party widget like ECTS Tracker), "telegram"
      for the bot, or null for a caller with no Origin header (a direct API
      call) or an answer logged before this field existed. */
  origin: string | null;
}

export interface ChangelogEntry {
  version: string;
  date: string;
  sections: Record<string, string[]>;
}

export interface VersionInfo {
  version: string;
  changelog: ChangelogEntry[];
}

export interface VisitorCount {
  unique_visitors: number;
}
