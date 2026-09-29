import {
  AdminConfig,
  AdminStats,
  BudgetFallbackEvent,
  ChatSource,
  IngestedDocumentInfo,
  AnswerStatus,
  NodeLatencyStats,
  OpsStatus,
  OriginBreakdown,
  PendingSubmission,
  RateLimitStats,
  RetrievalDiagnostic,
  ReviewedAnswer,
  SourceChange,
  SubmissionStatus,
  UsageAnalytics,
  VersionInfo,
  VisitorCount,
} from '../types';

// Set VITE_API_BASE_URL at build time to point the app at a deployed backend
// (e.g. VITE_API_BASE_URL=https://aeds.example.edu). Empty means same-origin,
// which is what you want when the API is served behind the same host as the
// UI. The localhost default only covers local development - with it hardcoded,
// every user other than the one running the server got a failed fetch.
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

function getToken(): string | null {
  return localStorage.getItem('access_token');
}

async function request<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { ...(options.headers as Record<string, string> || {}) };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });
  if (!response.ok) {
    // A 401 means the stored token is no longer usable. Dropping it here is
    // what lets the next load re-establish a session instead of retrying a
    // dead token on every request for the rest of the visit.
    if (response.status === 401 && token) localStorage.removeItem('access_token');
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${response.status}`);
  }
  if (response.status === 204) return null as T;
  return response.json();
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export function login(email: string, password: string): Promise<TokenResponse> {
  const form = new URLSearchParams();
  form.set('username', email);
  form.set('password', password);

  return fetch(`${API_BASE_URL}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: form,
  }).then(async (response) => {
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || 'Login failed');
    }
    return response.json();
  });
}

// No register() here on purpose: people using the assistant stay anonymous and
// never create accounts. /auth/register survives on the backend only to
// bootstrap the first admin on a fresh install, and refuses once one exists.

export interface Identity {
  id: number;
  email: string;
  role: 'admin' | 'user';
  /** True for an auto-provisioned anonymous visitor (no registered account). */
  is_guest: boolean;
}

/** Mints a fresh anonymous identity so a visitor gets their own threads and
    history without registering. Call once per browser, not per page load. */
export function createGuestSession(): Promise<TokenResponse> {
  return request('/auth/guest', { method: 'POST' });
}

export function getMe(): Promise<Identity> {
  return request('/auth/me');
}

export interface ChatApiResponse {
  thread_id: string;
  answer: string;
  sources: ChatSource[];
  auto_flagged_contribution: string | null;
  retrieval: RetrievalDiagnostic[];
  node_latencies: Record<string, number>;
  query_log_id: number | null;
  cached: boolean;
}

export function rateAnswer(queryLogId: number, rating: 1 | -1): Promise<void> {
  return request('/chat/feedback', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query_log_id: queryLogId, rating }),
  });
}

export function sendChatMessage(
  message: string,
  threadId: string | null,
  sourceIdFilter?: string | null
): Promise<ChatApiResponse> {
  return request('/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, thread_id: threadId, source_id_filter: sourceIdFilter || null }),
  });
}

function parseSseEvent(block: string): { event: string; data: any } {
  let event = 'message';
  let data = '';
  for (const line of block.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim();
    else if (line.startsWith('data:')) data += line.slice(5).trim();
  }
  return { event, data: data ? JSON.parse(data) : null };
}

export async function streamChatMessage(
  message: string,
  threadId: string | null,
  sourceIdFilter: string | null | undefined,
  { onToken, onDone }: { onToken: (text: string) => void; onDone: (data: any) => void }
): Promise<void> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(`${API_BASE_URL}/chat/stream`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ message, thread_id: threadId, source_id_filter: sourceIdFilter || null }),
  });
  if (!response.ok || !response.body) {
    // Same recovery as request(): streaming bypasses that helper entirely, so
    // without this a dead token would never get cleared from the chat path -
    // which is the one users actually spend their time on.
    if (response.status === 401 && token) localStorage.removeItem('access_token');
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let separatorIndex;
    while ((separatorIndex = buffer.indexOf('\n\n')) !== -1) {
      const block = buffer.slice(0, separatorIndex);
      buffer = buffer.slice(separatorIndex + 2);
      if (!block.trim()) continue;

      const { event, data } = parseSseEvent(block);
      if (event === 'token' && data) onToken(data.text);
      else if (event === 'done' && data) onDone(data);
    }
  }
}

export function submitFeedback(payload: {
  submission_type: 'new_info' | 'correction';
  source_id: string;
  content: string;
  related_chunk_id?: string | null;
}) {
  return request('/chat/submissions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export function fetchPendingSubmissions(
  statusFilter: SubmissionStatus | 'all' = 'pending'
): Promise<PendingSubmission[]> {
  return request(`/admin/pending?status_filter=${statusFilter}`);
}

export function updateSubmission(id: number, content: string, sourceId: string): Promise<PendingSubmission> {
  return request(`/admin/pending/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content, source_id: sourceId }),
  });
}

export function approveSubmission(id: number, adminNote?: string) {
  return request(`/admin/pending/${id}/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ admin_note: adminNote || null }),
  });
}

export function rejectSubmission(id: number, adminNote?: string) {
  return request(`/admin/pending/${id}/reject`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ admin_note: adminNote || null }),
  });
}

export interface RevokeResult {
  id: number;
  status: 'revoked';
  chunks_deleted: number;
  /** True when the chunk this correction had superseded was un-deprecated. */
  original_chunk_restored: boolean;
}

/** Removes an already-approved submission's content from the vector store. */
export function revokeSubmission(id: number, adminNote?: string): Promise<RevokeResult> {
  return request(`/admin/pending/${id}/revoke`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ admin_note: adminNote || null }),
  });
}

export interface UploadResult {
  filename: string;
  chunks_ingested: number;
  /** True when the content hash matched an already-ingested file (skipped). */
  unchanged: boolean;
}

export function uploadDocument(file: File): Promise<UploadResult> {
  const formData = new FormData();
  formData.append('file', file);
  return request('/admin/documents', { method: 'POST', body: formData });
}

export function listDocuments(): Promise<IngestedDocumentInfo[]> {
  return request('/admin/documents');
}

export function deleteDocument(filename: string) {
  return request(`/admin/documents/${encodeURIComponent(filename)}`, { method: 'DELETE' });
}

export function listSourceChanges(): Promise<SourceChange[]> {
  return request('/admin/source-changes');
}

/** Clears the flagged diff once an admin has reviewed it (and re-curated the
    file by hand, if warranted). Does not touch the document itself. */
export function dismissSourceChange(filename: string) {
  return request(`/admin/source-changes/${encodeURIComponent(filename)}/dismiss`, { method: 'POST' });
}

export function getConfig(): Promise<AdminConfig> {
  return request('/admin/config');
}

export function putConfig(payload: Partial<{
  llm_provider: string;
  gemini_model: string;
  openrouter_model: string;
  openrouter_fallback_model: string;
  daily_budget_fallback_provider: string;
  retrieval_top_k: number;
  rerank_top_k: number;
  conversation_history_window: number;
  system_prompt_override: string;
  reset_system_prompt: boolean;
}>): Promise<AdminConfig> {
  return request('/admin/config', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export function getBudgetFallbackEvents(): Promise<BudgetFallbackEvent[]> {
  return request('/admin/budget-fallback-events');
}

export function getStats(): Promise<AdminStats> {
  return request('/admin/stats');
}

export function getVersion(): Promise<VersionInfo> {
  return request('/version');
}

export function getVisitorCount(): Promise<VisitorCount> {
  return request('/visitors');
}

export function getAnalytics(days = 30): Promise<UsageAnalytics> {
  return request(`/admin/analytics?days=${days}`);
}

export function getOriginStats(days = 30): Promise<OriginBreakdown> {
  return request(`/admin/origin-stats?days=${days}`);
}

export function getOpsStatus(): Promise<OpsStatus> {
  return request('/admin/ops-status');
}

export function getRateLimitStats(days = 7): Promise<RateLimitStats> {
  return request(`/admin/rate-limit-stats?days=${days}`);
}

export function getNodeLatencyStats(days = 7): Promise<NodeLatencyStats> {
  return request(`/admin/node-latency-stats?days=${days}`);
}

export interface StaffUser {
  id: number;
  email: string;
  role: 'admin' | 'user';
  created_at: string;
  submissions: number;
  reviews: number;
}

export interface StaffUserList {
  users: StaffUser[];
  /** Anonymous visitors are counted, never listed - nothing identifies them. */
  anonymous_sessions: number;
}

export function listUsers(): Promise<StaffUserList> {
  return request('/admin/users');
}

export function createUser(payload: { email: string; password: string; role: 'admin' | 'user' }): Promise<StaffUser> {
  return request('/admin/users', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export function updateUser(id: number, payload: { role?: 'admin' | 'user'; password?: string }): Promise<StaffUser> {
  return request(`/admin/users/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export function deleteUser(id: number) {
  return request(`/admin/users/${id}`, { method: 'DELETE' });
}

export function listAnswers(status: AnswerStatus | 'all' = 'pending'): Promise<ReviewedAnswer[]> {
  return request(`/admin/answers?status_filter=${status}`);
}

/** Approve the answer, optionally replacing the model's text with a correction. */
export function approveAnswer(id: number, answer?: string, adminNote?: string): Promise<ReviewedAnswer> {
  return request(`/admin/answers/${id}/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ answer: answer ?? null, admin_note: adminNote ?? null }),
  });
}

export function rejectAnswer(id: number, adminNote?: string): Promise<ReviewedAnswer> {
  return request(`/admin/answers/${id}/reject`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ admin_note: adminNote ?? null }),
  });
}

export function deleteAnswer(id: number) {
  return request(`/admin/answers/${id}`, { method: 'DELETE' });
}
