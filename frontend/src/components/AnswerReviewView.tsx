import React, { useEffect, useState } from 'react';
import {
  MessagesSquare, CheckCircle2, XCircle, Clock, Filter, Pencil,
  RefreshCw, Trash2, Info, X, Save, Repeat,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ANSWER_MARKDOWN_COMPONENTS } from './markdown';
import { InjectionWarning } from './InjectionWarning';
import { AnswerStatus, ReviewedAnswer } from '../types';
import { approveAnswer, deleteAnswer, listAnswers, rejectAnswer } from '../api/client';

type FilterStatus = AnswerStatus | 'all';

const STATUS_STYLE: Record<AnswerStatus, string> = {
  pending: 'bg-amber-500/20 text-amber-600 dark:text-amber-300 border-amber-500/30',
  approved: 'bg-emerald-500/20 text-emerald-600 dark:text-emerald-300 border-emerald-500/30',
  rejected: 'bg-rose-500/20 text-rose-600 dark:text-rose-300 border-rose-500/30',
};

const STATUS_ICON: Record<AnswerStatus, React.ReactNode> = {
  pending: <Clock className="w-3.5 h-3.5" />,
  approved: <CheckCircle2 className="w-3.5 h-3.5" />,
  rejected: <XCircle className="w-3.5 h-3.5" />,
};

/** A short, readable label for where the question came in from - "Telegram"
    as-is, a bare Origin URL reduced to its hostname (so a long
    "https://ofurkancoban.github.io" reads as "ofurkancoban.github.io"), or
    null for a caller that sent no Origin header at all (a direct API call,
    or an answer logged before this field existed) - nothing meaningful to
    show in that case. */
function formatOrigin(origin: string | null): string | null {
  if (!origin) return null;
  if (origin === 'telegram') return 'Telegram';
  try {
    return new URL(origin).hostname;
  } catch {
    return origin;
  }
}

interface AnswerReviewViewProps {
  /** Lets the navbar badge refresh once an item leaves the queue. */
  onQueueChange?: () => void;
}

export const AnswerReviewView: React.FC<AnswerReviewViewProps> = ({ onQueueChange }) => {
  const [items, setItems] = useState<ReviewedAnswer[]>([]);
  const [filter, setFilter] = useState<FilterStatus>('pending');
  const [isLoading, setIsLoading] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [draft, setDraft] = useState('');

  const load = async (status: FilterStatus = filter) => {
    setIsLoading(true);
    try {
      setItems(await listAnswers(status));
    } catch (e) {
      console.error('Failed to load answers:', e);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    load(filter);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter]);

  const finish = async () => {
    setEditingId(null);
    await load();
    onQueueChange?.();
  };

  const handleApprove = async (item: ReviewedAnswer) => {
    setBusyId(item.id);
    try {
      await approveAnswer(item.id, editingId === item.id ? draft : undefined);
      await finish();
    } catch (e: any) {
      alert(e.message || 'Could not approve');
    } finally {
      setBusyId(null);
    }
  };

  const handleReject = async (item: ReviewedAnswer) => {
    setBusyId(item.id);
    try {
      await rejectAnswer(item.id);
      await finish();
    } catch (e: any) {
      alert(e.message || 'Could not reject');
    } finally {
      setBusyId(null);
    }
  };

  const handleDelete = async (item: ReviewedAnswer) => {
    if (!confirm('Delete this record entirely?\n\nRejected answers are worth keeping as evidence of what went wrong.')) return;
    setBusyId(item.id);
    try {
      await deleteAnswer(item.id);
      await finish();
    } catch (e: any) {
      alert(e.message || 'Could not delete');
    } finally {
      setBusyId(null);
    }
  };

  const pendingCount = items.filter((i) => i.status === 'pending').length;

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">

      <div className="glass rounded-3xl p-6 shadow-2xl space-y-4">
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center space-x-2.5">
              <div className="w-8 h-8 rounded-xl bg-accent-600/20 border border-accent-500/30 flex items-center justify-center text-accent-500 dark:text-accent-400">
                <MessagesSquare className="w-5 h-5" />
              </div>
              <h1 className="text-lg font-extrabold text-[var(--text)] tracking-tight">Answer Review</h1>
            </div>
            <p className="text-xs text-[var(--text-secondary)]">
              Questions students asked, with the answer that was given. Approving one makes it the
              reply everyone gets for that question from then on.
            </p>
          </div>

          <button
            onClick={() => load()}
            className="flex items-center justify-center space-x-2 glass-well hover:bg-[var(--bg-inset)]/70 text-[var(--text-secondary)] text-xs font-bold px-4 py-2.5 rounded-2xl transition-all cursor-pointer shadow-md shrink-0"
          >
            <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
            <span>Refresh</span>
          </button>
        </div>

        {/* States the one thing that is easy to get wrong about this screen:
            approving does not re-run the pipeline, it fixes the reply. */}
        <div className="flex items-start gap-2.5 text-[11px] text-[var(--text-muted)] glass-well rounded-2xl p-3">
          <Info className="w-3.5 h-3.5 text-accent-500 dark:text-accent-400 shrink-0 mt-0.5" />
          <span>
            Nothing here is reused until you approve it, so a wrong answer cannot spread to later
            askers. Edit before approving to correct it - your text is what gets served, not the
            model's. Rejected entries are kept as a record of what went wrong and are never replayed.
          </span>
        </div>
      </div>

      <div className="flex items-center glass p-2 rounded-2xl shadow-xl">
        <div className="flex flex-wrap items-center gap-1.5 text-xs">
          {(['pending', 'approved', 'rejected', 'all'] as FilterStatus[]).map((s) => (
            <button
              key={s}
              onClick={() => setFilter(s)}
              className={`px-4 py-2 rounded-xl font-bold transition-all cursor-pointer flex items-center space-x-2 capitalize ${
                filter === s
                  ? 'bg-accent-600/20 text-accent-600 dark:text-accent-300 border border-accent-500/40 font-extrabold shadow-sm'
                  : 'text-[var(--text-muted)] hover:text-[var(--text)] hover:bg-[var(--bg-inset)]'
              }`}
            >
              {s === 'all' ? <Filter className="w-3.5 h-3.5" /> : STATUS_ICON[s]}
              <span>{s}{s === 'pending' && pendingCount > 0 ? ` (${pendingCount})` : ''}</span>
            </button>
          ))}
        </div>
      </div>

      {items.length === 0 ? (
        <div className="glass rounded-2xl p-12 text-center text-[var(--text-muted)] space-y-3">
          <MessagesSquare className="w-10 h-10 text-[var(--text-faint)] mx-auto" />
          <p className="text-sm font-medium">
            {isLoading ? 'Loading...' : 'Nothing here for this filter.'}
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {items.map((item) => {
            const busy = busyId === item.id;
            const isEditing = editingId === item.id;
            return (
              <div
                key={item.id}
                className={`bg-[var(--bg-subtle)] border rounded-2xl p-5 space-y-3 backdrop-blur-md transition-all ${
                  isEditing
                    ? 'border-accent-500/50 bg-accent-500/5 shadow-lg shadow-accent-500/10'
                    : item.status === 'pending'
                    ? 'border-amber-500/30 bg-amber-500/5'
                    : item.status === 'approved'
                    ? 'border-emerald-500/30 bg-emerald-500/5 opacity-90'
                    : 'border-rose-500/30 bg-rose-500/5 opacity-70'
                }`}
              >
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border)] pb-3">
                  <div className="flex items-center gap-2 text-[10px] text-[var(--text-muted)] font-mono">
                    <span>{new Date(item.created_at).toLocaleString('en-US')}</span>
                    {formatOrigin(item.origin) && (
                      <span className="px-1.5 py-0.5 rounded-full bg-[var(--bg-inset)] border border-[var(--border)]">
                        {formatOrigin(item.origin)}
                      </span>
                    )}
                    {item.sources.length > 0 && <span>· {item.sources.join(', ')}</span>}
                    {item.hit_count > 0 && (
                      <span className="flex items-center gap-1 text-accent-500 dark:text-accent-300">
                        <Repeat className="w-3 h-3" />served {item.hit_count}x
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-1.5">
                    {item.edited && (
                      <span className="text-[9px] font-extrabold uppercase tracking-wide px-1.5 py-0.5 rounded-full bg-accent-500/15 text-accent-600 dark:text-accent-300 border border-accent-500/30">
                        corrected
                      </span>
                    )}
                    <span className={`text-[11px] font-bold px-3 py-1 rounded-full flex items-center space-x-1 border ${STATUS_STYLE[item.status]}`}>
                      {STATUS_ICON[item.status]}
                      <span className="capitalize">{item.status}</span>
                    </span>
                  </div>
                </div>

                <p className="text-sm font-bold text-[var(--text)]">{item.question}</p>

                <InjectionWarning markers={item.injection_markers} />

                {isEditing ? (
                  <textarea
                    rows={10}
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    className="w-full glass-well rounded-2xl p-4 text-xs font-mono text-[var(--text-secondary)] focus:outline-none focus:border-accent-500/60 leading-relaxed"
                  />
                ) : (
                  <div className="glass-well rounded-2xl p-4">
                    <div className="answer-prose max-w-none text-xs text-[var(--text-secondary)]">
                      <ReactMarkdown remarkPlugins={[remarkGfm]} components={ANSWER_MARKDOWN_COMPONENTS}>{item.answer}</ReactMarkdown>
                    </div>
                  </div>
                )}

                {item.edited && !isEditing && item.original_answer && (
                  <details className="glass-well rounded-2xl overflow-hidden">
                    <summary className="cursor-pointer px-4 py-2.5 text-[11px] font-bold text-[var(--text-muted)] hover:text-[var(--text-secondary)]">
                      Show what the model originally answered
                    </summary>
                    <p className="px-4 pb-4 text-[11px] font-mono text-[var(--text-faint)] whitespace-pre-wrap leading-relaxed">
                      {item.original_answer}
                    </p>
                  </details>
                )}

                <div className="flex flex-wrap items-center justify-end gap-2 pt-1">
                  {isEditing ? (
                    <>
                      <button
                        onClick={() => setEditingId(null)}
                        disabled={busy}
                        className="px-3.5 py-2 bg-[var(--bg-inset)] hover:bg-[var(--bg-inset)]/70 text-[var(--text-secondary)] rounded-xl text-xs font-semibold cursor-pointer flex items-center gap-1.5"
                      >
                        <X className="w-3.5 h-3.5" />Cancel
                      </button>
                      <button
                        onClick={() => handleApprove(item)}
                        disabled={busy}
                        className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white border border-emerald-400/40 rounded-xl text-xs font-bold shadow-lg shadow-emerald-600/20 cursor-pointer flex items-center gap-1.5 disabled:opacity-50"
                      >
                        <Save className="w-4 h-4" />Save &amp; Approve
                      </button>
                    </>
                  ) : (
                    <>
                      <button
                        onClick={() => { setEditingId(item.id); setDraft(item.answer); }}
                        disabled={busy}
                        className="px-3.5 py-2 bg-accent-500/20 hover:bg-accent-500/30 text-accent-600 dark:text-accent-300 border border-accent-500/40 rounded-xl text-xs font-semibold cursor-pointer flex items-center gap-1.5"
                      >
                        <Pencil className="w-3.5 h-3.5" />Correct
                      </button>
                      {item.status !== 'rejected' && (
                        <button
                          onClick={() => handleReject(item)}
                          disabled={busy}
                          className="px-4 py-2 bg-rose-500/20 hover:bg-rose-500/30 text-rose-600 dark:text-rose-300 border border-rose-500/40 rounded-xl text-xs font-semibold cursor-pointer flex items-center gap-1.5"
                        >
                          <XCircle className="w-4 h-4" />Reject
                        </button>
                      )}
                      {item.status !== 'approved' && (
                        <button
                          onClick={() => handleApprove(item)}
                          disabled={busy}
                          className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white border border-emerald-400/40 rounded-xl text-xs font-bold shadow-lg shadow-emerald-600/20 cursor-pointer flex items-center gap-1.5 disabled:opacity-50"
                        >
                          <CheckCircle2 className="w-4 h-4" />{busy ? 'Saving...' : 'Approve'}
                        </button>
                      )}
                      <button
                        onClick={() => handleDelete(item)}
                        disabled={busy}
                        title="Delete this record"
                        className="p-1.5 text-[var(--text-faint)] hover:text-rose-500 hover:bg-[var(--bg-inset)] rounded-xl transition-colors cursor-pointer"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
