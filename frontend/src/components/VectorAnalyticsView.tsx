import React, { useEffect, useState } from 'react';
import { BarChart2, Activity, RefreshCw, Zap, AlertTriangle, ThumbsUp, ThumbsDown, Database, Globe, HeartPulse, Gauge, ShieldAlert } from 'lucide-react';
import { AdminStats, ChatQueryResult, OpsStatus, OriginBreakdown, RateLimitStats, UsageAnalytics } from '../types';
import { getAnalytics, getOpsStatus, getOriginStats, getRateLimitStats, getStats } from '../api/client';

// A small fixed palette, cycled by rank so the biggest origin always gets
// the same accent colour across refreshes rather than reshuffling.
const ORIGIN_BAR_COLORS = ['bg-accent-500', 'bg-emerald-500', 'bg-amber-500', 'bg-rose-500', 'bg-sky-500'];

interface VectorAnalyticsViewProps {
  latestResult: ChatQueryResult | null;
}

export const VectorAnalyticsView: React.FC<VectorAnalyticsViewProps> = ({ latestResult }) => {
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [analytics, setAnalytics] = useState<UsageAnalytics | null>(null);
  const [originStats, setOriginStats] = useState<OriginBreakdown | null>(null);
  const [opsStatus, setOpsStatus] = useState<OpsStatus | null>(null);
  const [rateLimitStats, setRateLimitStats] = useState<RateLimitStats | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  // Silent (no spinner) by default - only the manual Refresh button and the
  // very first load should show one. A spinner flashing every 30s on its
  // own would read as the page having a problem, not as it staying current.
  const load = async (showSpinner = false) => {
    if (showSpinner) setIsLoading(true);
    try {
      const [statsData, analyticsData, originData, opsData, rateLimitData] = await Promise.all([
        getStats(),
        getAnalytics(),
        getOriginStats(),
        getOpsStatus(),
        getRateLimitStats(),
      ]);
      setStats(statsData);
      setAnalytics(analyticsData);
      setOriginStats(originData);
      setOpsStatus(opsData);
      setRateLimitStats(rateLimitData);
    } catch (e) {
      console.error('Failed to load stats:', e);
    } finally {
      if (showSpinner) setIsLoading(false);
    }
  };

  useEffect(() => {
    load(true);

    // Corpus size and usage counts change from actions elsewhere (another
    // admin ingesting a document, a student asking questions) that this tab
    // has no other way to hear about - a 30s poll is enough for a
    // monitoring view like this without hammering the admin-only endpoints
    // it calls. Only runs while this tab is actually mounted (the admin
    // shell unmounts inactive tabs), so it costs nothing when unused.
    const interval = setInterval(() => load(false), 30_000);
    return () => clearInterval(interval);
  }, []);

  // A cache hit returns no node timings at all, and summing that empty object
  // gave 0 - which the panel then displayed as a genuine "0ms end-to-end"
  // rather than saying no pipeline ran.
  const nodeLatencies = latestResult?.nodeLatencies ?? {};
  const measuredNodes = Object.keys(nodeLatencies).length > 0;
  const totalLatency = measuredNodes
    ? Object.values(nodeLatencies).reduce((sum, ms) => sum + ms, 0)
    : null;

  const topRerankScore = latestResult?.retrieval?.length
    ? Math.max(...latestResult.retrieval.map((r) => r.rerank_score ?? -Infinity))
    : null;

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">

      <div className="glass rounded-3xl p-6 shadow-2xl flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center space-x-2.5">
            <div className="w-8 h-8 rounded-xl bg-accent-600/20 border border-accent-500/30 flex items-center justify-center text-accent-500 dark:text-accent-400">
              <BarChart2 className="w-5 h-5 text-accent-500 dark:text-accent-400" />
            </div>
            <h1 className="text-lg font-extrabold text-[var(--text)] tracking-tight">Vector Space &amp; RAG Analytics</h1>
          </div>
          <p className="text-xs text-[var(--text-muted)] mt-1">
            Real corpus statistics and the retrieval diagnostics from the last chat query.
          </p>
        </div>

        <button
          onClick={() => load(true)}
          className="flex items-center space-x-1.5 text-xs font-bold text-[var(--text-secondary)] hover:text-[var(--text)] bg-[var(--bg-inset)] hover:bg-[var(--bg-inset)]/70 px-4 py-2.5 rounded-2xl border border-accent-500/20 transition-all cursor-pointer shadow-md shrink-0"
        >
          <RefreshCw className={`w-3.5 h-3.5 text-accent-500 dark:text-accent-400 ${isLoading ? 'animate-spin' : ''}`} />
          <span>Refresh</span>
        </button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="glass p-5 rounded-3xl space-y-2 shadow-2xl">
          <span className="text-[10px] font-extrabold text-[var(--text-muted)] uppercase tracking-widest">Total Vector Chunks</span>
          <div className="text-2xl font-extrabold text-[var(--text)] font-mono">{stats?.total_chunks ?? '—'}</div>
          <span className="text-[11px] text-emerald-600 dark:text-emerald-400 font-bold">{stats?.total_sources ?? 0} source documents</span>
        </div>

        <div className="glass p-5 rounded-3xl space-y-2 shadow-2xl">
          <span className="text-[10px] font-extrabold text-[var(--text-muted)] uppercase tracking-widest">Embedding Model</span>
          <div className="text-sm font-bold text-accent-600 dark:text-accent-300 font-mono truncate">{stats?.embedding_model ?? '—'}</div>
          <span className="text-[11px] text-[var(--text-muted)]">{stats?.embedding_dimension ?? '—'}-dim vectors</span>
        </div>

        <div className="glass p-5 rounded-3xl space-y-2 shadow-2xl">
          <span className="text-[10px] font-extrabold text-[var(--text-muted)] uppercase tracking-widest">Last Query Latency</span>
          <div className="text-2xl font-extrabold text-[var(--text)] font-mono">
            {totalLatency != null
              ? `${Math.round(totalLatency)}ms`
              : latestResult?.cached
              ? 'Cached'
              : 'N/A'}
          </div>
          <span className="text-[11px] text-[var(--text-muted)]">
            {totalLatency != null
              ? 'Retrieve + generate + contribution check'
              : latestResult?.cached
              ? 'Answered from cache - the pipeline did not run'
              : 'Ask a question to measure'}
          </span>
        </div>

        <div className="glass p-5 rounded-3xl space-y-2 shadow-2xl">
          <span className="text-[10px] font-extrabold text-[var(--text-muted)] uppercase tracking-widest">Top Rerank Score</span>
          <div className="text-2xl font-extrabold text-emerald-600 dark:text-emerald-400 font-mono">
            {topRerankScore != null && Number.isFinite(topRerankScore) ? topRerankScore.toFixed(2) : 'N/A'}
          </div>
          <span className="text-[11px] text-[var(--text-muted)]">Cross-encoder relevance score</span>
        </div>
      </div>

      {stats && stats.expired_documents > 0 && (
        <div className="rounded-3xl p-5 border border-amber-500/40 bg-amber-500/10 flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-amber-500 shrink-0 mt-0.5" />
          <div className="text-xs space-y-1">
            {/* The noun was already pluralised here but the pronouns were
                not, so a single expired file read "1 document past their
                validity date". The body text is written without pronouns
                instead, which reads correctly for any count. */}
            <p className="font-extrabold text-amber-700 dark:text-amber-300">
              {stats.expired_documents === 1
                ? '1 document past its validity date'
                : `${stats.expired_documents} documents past their validity date`}
            </p>
            <p className="text-[var(--text-secondary)]">
              The content describes a cycle that has already closed. Re-scrape and re-upload to
              refresh the corpus. Until then the assistant still answers from this material but
              marks it as out of date, rather than presenting those dates as current.
            </p>
          </div>
        </div>
      )}

      {analytics && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="glass rounded-3xl p-6 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between border-b border-accent-500/10 pb-3.5">
              <h2 className="text-sm font-extrabold text-[var(--text)] flex items-center space-x-2">
                <Activity className="w-4 h-4 text-accent-500 dark:text-accent-400" />
                <span>Usage (last 30 days)</span>
              </h2>
              <span className="text-[11px] font-mono text-[var(--text-muted)]">
                {analytics.total_queries} queries
              </span>
            </div>

            <div className="grid grid-cols-2 gap-3 text-xs">
              <div className="glass-well rounded-2xl p-3 space-y-1">
                <span className="text-[10px] uppercase tracking-widest text-[var(--text-muted)] font-extrabold">Cache hit rate</span>
                <div className="text-xl font-extrabold font-mono text-accent-600 dark:text-accent-300 flex items-center gap-1.5">
                  <Database className="w-4 h-4" />
                  {Math.round(analytics.cache_hit_rate * 100)}%
                </div>
                <span className="text-[10px] text-[var(--text-muted)]">LLM calls skipped entirely</span>
              </div>
              <div className="glass-well rounded-2xl p-3 space-y-1">
                <span className="text-[10px] uppercase tracking-widest text-[var(--text-muted)] font-extrabold">Avg latency</span>
                <div className="text-xl font-extrabold font-mono text-[var(--text)]">
                  {analytics.avg_latency_ms}ms
                </div>
                <span className="text-[10px] text-[var(--text-muted)]">excludes cache hits</span>
              </div>
              <div className="glass-well rounded-2xl p-3 space-y-1">
                <span className="text-[10px] uppercase tracking-widest text-[var(--text-muted)] font-extrabold">Ratings</span>
                <div className="text-xl font-extrabold font-mono flex items-center gap-3">
                  <span className="text-emerald-600 dark:text-emerald-400 flex items-center gap-1">
                    <ThumbsUp className="w-4 h-4" />{analytics.thumbs_up}
                  </span>
                  <span className="text-rose-600 dark:text-rose-400 flex items-center gap-1">
                    <ThumbsDown className="w-4 h-4" />{analytics.thumbs_down}
                  </span>
                </div>
              </div>
              <div className="glass-well rounded-2xl p-3 space-y-1">
                <span className="text-[10px] uppercase tracking-widest text-[var(--text-muted)] font-extrabold">Unanswered</span>
                <div className="text-xl font-extrabold font-mono text-amber-600 dark:text-amber-400">
                  {analytics.unanswered_queries}
                </div>
                <span className="text-[10px] text-[var(--text-muted)]">corpus had no answer</span>
              </div>

              {/* A budget of 0 means no ceiling - the default when a local
                  model is serving, since there is no external quota to ration.
                  Showing a usage bar against 0 would divide by zero and render
                  a permanently red "over budget" meter. */}
              {stats && (
                <div className="glass-well rounded-2xl p-3 space-y-1.5 col-span-2">
                  <div className="flex items-baseline justify-between">
                    <span className="text-[10px] uppercase tracking-widest text-[var(--text-muted)] font-extrabold">
                      LLM requests today
                    </span>
                    <span className="font-mono text-xs font-extrabold text-[var(--text)]">
                      {stats.llm_calls_today}
                      {stats.llm_daily_budget > 0 && ` / ${stats.llm_daily_budget}`}
                    </span>
                  </div>

                  {stats.llm_daily_budget > 0 && (
                    <div className="w-full h-2 rounded-full overflow-hidden bg-black/10 dark:bg-white/10">
                      <div
                        className={`h-full rounded-full transition-all ${
                          stats.llm_calls_today / stats.llm_daily_budget > 0.85
                            ? 'bg-rose-500'
                            : stats.llm_calls_today / stats.llm_daily_budget > 0.6
                            ? 'bg-amber-500'
                            : 'bg-emerald-500'
                        }`}
                        style={{
                          width: `${Math.min(100, (stats.llm_calls_today / stats.llm_daily_budget) * 100)}%`,
                        }}
                      />
                    </div>
                  )}

                  {/* Requests, not questions: a turn costs 2-3 depending on
                      routing, and cache hits cost none. */}
                  <span className="text-[10px] text-[var(--text-muted)]">
                    {stats.llm_daily_budget > 0
                      ? 'Requests issued, not questions asked - cache hits cost none. Resets at 00:00 UTC.'
                      : `No daily ceiling - ${stats.llm_provider} is unmetered, so requests cost CPU time rather than quota.`}
                  </span>
                </div>
              )}
            </div>

            <div className="space-y-2 pt-1">
              <span className="text-[10px] font-extrabold text-accent-500 dark:text-accent-400 uppercase tracking-wider">
                Most asked
              </span>
              {analytics.top_questions.length === 0 ? (
                <p className="text-[11px] text-[var(--text-faint)]">No questions logged yet.</p>
              ) : (
                analytics.top_questions.map((q, idx) => (
                  <div key={idx} className="flex items-center justify-between gap-3 text-[11px] glass-well rounded-xl px-3 py-2">
                    <span className="truncate text-[var(--text-secondary)]">{q.question}</span>
                    <span className="font-mono font-bold text-[var(--text-muted)] shrink-0">{q.count}x</span>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Content gaps: the questions users asked that the documents could
              not answer. This is the highest-signal list in the whole admin UI
              - it says exactly which documents are still missing, from real
              demand rather than guesswork. */}
          <div className="glass rounded-3xl p-6 space-y-4 shadow-2xl">
            <div className="border-b border-accent-500/10 pb-3.5">
              <h2 className="text-sm font-extrabold text-[var(--text)] flex items-center space-x-2">
                <AlertTriangle className="w-4 h-4 text-amber-500" />
                <span>Content Gaps</span>
              </h2>
              <p className="text-[11px] text-[var(--text-muted)] mt-0.5">
                Questions the corpus could not answer - add documents covering these.
              </p>
            </div>

            {analytics.content_gaps.length === 0 ? (
              <p className="text-[11px] text-[var(--text-faint)] py-6 text-center">
                No unanswered questions logged. Every question so far was covered by the documents.
              </p>
            ) : (
              <div className="space-y-2">
                {analytics.content_gaps.map((q, idx) => (
                  <div key={idx} className="flex items-center justify-between gap-3 text-[11px] rounded-xl px-3 py-2 border border-amber-500/25 bg-amber-500/5">
                    <span className="truncate text-[var(--text-secondary)]">{q.question}</span>
                    <span className="font-mono font-bold text-amber-600 dark:text-amber-400 shrink-0">{q.count}x</span>
                  </div>
                ))}
              </div>
            )}

            {analytics.thumbs_down_questions.length > 0 && (
              <div className="space-y-2 pt-2">
                <span className="text-[10px] font-extrabold text-rose-500 uppercase tracking-wider">
                  Rated unhelpful
                </span>
                {analytics.thumbs_down_questions.map((q, idx) => (
                  <div key={idx} className="text-[11px] rounded-xl px-3 py-2 border border-rose-500/25 bg-rose-500/5 text-[var(--text-secondary)] truncate">
                    {q}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {originStats && originStats.total_queries > 0 && (
        <div className="glass rounded-3xl p-6 space-y-4 shadow-2xl">
          <div className="flex items-center justify-between border-b border-accent-500/10 pb-3.5">
            <h2 className="text-sm font-extrabold text-[var(--text)] flex items-center space-x-2">
              <Globe className="w-4 h-4 text-accent-500 dark:text-accent-400" />
              <span>Traffic by Origin (last 30 days)</span>
            </h2>
            <span className="text-[11px] font-mono text-[var(--text-muted)]">
              {originStats.total_queries} queries
            </span>
          </div>

          <div className="space-y-2.5">
            {originStats.by_origin.map((row, idx) => (
              <div key={row.origin} className="space-y-1">
                <div className="flex items-center justify-between text-[11px]">
                  <span className="font-semibold text-[var(--text-secondary)] truncate">{row.origin}</span>
                  <span className="font-mono font-bold text-[var(--text-muted)] shrink-0">
                    {row.count} ({Math.round(row.percent * 100)}%)
                    <span className="text-[var(--text-faint)] ml-1.5">· {Math.round(row.cache_hit_rate * 100)}% cached</span>
                  </span>
                </div>
                <div className="w-full h-2 rounded-full overflow-hidden bg-black/10 dark:bg-white/10">
                  <div
                    className={`h-full rounded-full transition-all ${ORIGIN_BAR_COLORS[idx % ORIGIN_BAR_COLORS.length]}`}
                    style={{ width: `${Math.max(2, row.percent * 100)}%` }}
                  />
                </div>
              </div>
            ))}
          </div>

          {originStats.daily_totals.length > 1 && (
            <div className="pt-2 space-y-1.5">
              <span className="text-[10px] font-extrabold text-[var(--text-muted)] uppercase tracking-widest">
                Daily volume
              </span>
              <div className="flex items-end gap-0.5 h-12">
                {originStats.daily_totals.map((day) => {
                  const max = Math.max(...originStats.daily_totals.map((d) => d.count));
                  return (
                    <div
                      key={day.date}
                      title={`${day.date}: ${day.count}`}
                      className="flex-1 bg-accent-500/60 hover:bg-accent-500 rounded-t transition-all"
                      style={{ height: `${Math.max(6, (day.count / max) * 100)}%` }}
                    />
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {opsStatus && (opsStatus.provider_usage.length > 0 || opsStatus.system_health.length > 0) && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="glass rounded-3xl p-6 space-y-3 shadow-2xl">
            <h2 className="text-sm font-extrabold text-[var(--text)] flex items-center space-x-2 border-b border-accent-500/10 pb-3.5">
              <Gauge className="w-4 h-4 text-accent-500 dark:text-accent-400" />
              <span>LLM Budget by Provider</span>
            </h2>
            <div className="space-y-2.5">
              {opsStatus.provider_usage.map((p) => {
                const ratio = p.daily_budget > 0 ? p.usage_today / p.daily_budget : 0;
                return (
                  <div key={p.provider} className="space-y-1">
                    <div className="flex items-center justify-between text-[11px]">
                      <span className="font-semibold text-[var(--text-secondary)] capitalize">{p.provider}</span>
                      <span className="font-mono font-bold text-[var(--text-muted)]">
                        {p.usage_today}{p.daily_budget > 0 ? ` / ${p.daily_budget}` : ' (unmetered)'}
                      </span>
                    </div>
                    {p.daily_budget > 0 && (
                      <div className="w-full h-2 rounded-full overflow-hidden bg-black/10 dark:bg-white/10">
                        <div
                          className={`h-full rounded-full transition-all ${
                            ratio > 0.85 ? 'bg-rose-500' : ratio > 0.6 ? 'bg-amber-500' : 'bg-emerald-500'
                          }`}
                          style={{ width: `${Math.min(100, ratio * 100)}%` }}
                        />
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          <div className="glass rounded-3xl p-6 space-y-3 shadow-2xl">
            <h2 className="text-sm font-extrabold text-[var(--text)] flex items-center space-x-2 border-b border-accent-500/10 pb-3.5">
              <HeartPulse className="w-4 h-4 text-accent-500 dark:text-accent-400" />
              <span>VPS Host Health</span>
            </h2>
            {opsStatus.system_health.length === 0 ? (
              <p className="text-[11px] text-[var(--text-faint)]">
                No checks recorded yet - scripts/system_health_check.py runs every 15 minutes.
              </p>
            ) : (
              <div className="space-y-2">
                {opsStatus.system_health.map((check) => (
                  <div
                    key={check.check_name}
                    className={`flex items-center justify-between text-[11px] rounded-xl px-3 py-2 border ${
                      check.is_breached
                        ? 'border-rose-500/30 bg-rose-500/10'
                        : 'border-emerald-500/20 bg-emerald-500/5'
                    }`}
                  >
                    <span className="font-semibold capitalize text-[var(--text-secondary)]">{check.check_name}</span>
                    <span className={`font-mono font-bold ${check.is_breached ? 'text-rose-600 dark:text-rose-400' : 'text-emerald-600 dark:text-emerald-400'}`}>
                      {check.is_breached ? 'breached' : 'healthy'}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {rateLimitStats && rateLimitStats.by_limiter.length > 0 && (
        <div className="glass rounded-3xl p-6 space-y-3 shadow-2xl">
          <h2 className="text-sm font-extrabold text-[var(--text)] flex items-center space-x-2 border-b border-accent-500/10 pb-3.5">
            <ShieldAlert className="w-4 h-4 text-amber-500" />
            <span>Rate Limit Rejections (last {rateLimitStats.days} days)</span>
          </h2>
          <p className="text-[11px] text-[var(--text-muted)] -mt-1">
            How often each limiter has turned a request away - a limiter with zero here is not doing
            anything; one with rejections every day may be worth loosening.
          </p>
          <div className="flex flex-wrap gap-2 pt-1">
            {rateLimitStats.by_limiter.map((row) => (
              <div
                key={row.limiter_name}
                className="flex items-center gap-2 text-[11px] rounded-xl px-3 py-2 border border-amber-500/25 bg-amber-500/5"
              >
                <span className="font-semibold text-[var(--text-secondary)]">{row.limiter_name}</span>
                <span className="font-mono font-bold text-amber-600 dark:text-amber-400">{row.total_rejections}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="glass p-5 rounded-3xl space-y-2 shadow-2xl">
        <span className="text-[10px] font-extrabold text-[var(--text-muted)] uppercase tracking-widest">Reranker &amp; Chat Model</span>
        <div className="flex flex-wrap gap-4 text-xs font-mono text-[var(--text-secondary)]">
          <span>Reranker: <strong className="text-accent-600 dark:text-accent-300">{stats?.reranker_model ?? '—'}</strong></span>
          <span>
            Chat model: <strong className="text-accent-600 dark:text-accent-300">{stats?.llm_model ?? '—'}</strong>
            {stats?.llm_provider && <span className="text-[var(--text-muted)]"> ({stats.llm_provider})</span>}
          </span>
          <span>Pending submissions: <strong className="text-amber-600 dark:text-amber-300">{stats?.pending_submissions ?? '—'}</strong></span>
        </div>
      </div>

      <div className="glass rounded-3xl p-6 space-y-4 shadow-2xl">
        <div className="flex items-center justify-between border-b border-accent-500/10 pb-3.5">
          <div>
            <h2 className="text-sm font-extrabold text-[var(--text)] flex items-center space-x-2">
              <Activity className="w-4 h-4 text-accent-500 dark:text-accent-400" />
              <span>Last Query Retrieval Breakdown</span>
            </h2>
            <p className="text-xs text-[var(--text-muted)] mt-0.5">
              {latestResult ? `Query: "${latestResult.query}"` : 'Ask a question in the chat tab to see retrieval diagnostics here.'}
            </p>
          </div>
        </div>

        {!latestResult || latestResult.retrieval.length === 0 ? (
          <div className="py-16 text-center text-[var(--text-faint)] text-xs">
            No retrieval data yet - run a query in the Chat tab.
          </div>
        ) : (
          <div className="space-y-3 max-h-96 overflow-y-auto pr-1">
            {latestResult.retrieval.map((item, idx) => {
              const scorePercent = item.rerank_score != null ? Math.max(0, Math.min(100, (item.rerank_score + 5) * 10)) : 0;
              return (
                <div key={idx} className="p-3.5 rounded-xl border border-accent-400/30 bg-accent-600/10 space-y-2 backdrop-blur-sm">
                  <div className="flex items-center justify-between text-xs">
                    <div className="flex items-center space-x-2 overflow-hidden">
                      <span className="font-mono font-bold text-[var(--text-muted)] text-[11px]">#{idx + 1}</span>
                      <span className="font-semibold text-[var(--text-secondary)] truncate">{item.source_id}</span>
                    </div>
                    <div className="flex items-center space-x-3 shrink-0 font-mono text-xs">
                      {item.rerank_score != null && (
                        <span className="text-emerald-600 dark:text-emerald-400 font-bold flex items-center gap-1">
                          <Zap className="w-3 h-3" />
                          rerank {item.rerank_score.toFixed(2)}
                        </span>
                      )}
                      {item.hybrid_score != null && (
                        <span className="text-accent-600 dark:text-accent-300">hybrid {item.hybrid_score.toFixed(3)}</span>
                      )}
                    </div>
                  </div>
                  <div className="w-full bg-black/5 dark:bg-white/5 rounded-full h-2 overflow-hidden border border-black/10 dark:border-white/10">
                    <div className="h-full rounded-full bg-gradient-to-r from-accent-500 to-emerald-400 transition-all duration-500" style={{ width: `${scorePercent}%` }} />
                  </div>
                  <p className="text-[11px] font-mono text-[var(--text-muted)] line-clamp-1">"{item.snippet}"</p>
                </div>
              );
            })}
          </div>
        )}
      </div>

    </div>
  );
};
