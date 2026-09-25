import React, { useEffect, useState } from 'react';
import {
  ShieldCheck,
  CheckCircle2,
  XCircle,
  Clock,
  Filter,
  Pencil,
  Save,
  X,
  RefreshCw,
  Undo2,
} from 'lucide-react';
import { InjectionWarning } from './InjectionWarning';
import { PendingSubmission, SubmissionStatus } from '../types';
import {
  approveSubmission,
  fetchPendingSubmissions,
  rejectSubmission,
  revokeSubmission,
  updateSubmission,
} from '../api/client';

type FilterStatus = SubmissionStatus | 'all';

const STATUS_STYLES: Record<SubmissionStatus, string> = {
  pending: 'bg-amber-500/20 text-amber-600 dark:text-amber-300 border-amber-500/30',
  approved: 'bg-emerald-500/20 text-emerald-600 dark:text-emerald-300 border-emerald-500/30',
  rejected: 'bg-red-500/20 text-red-600 dark:text-red-300 border-red-500/30',
  revoked: 'bg-slate-500/20 text-slate-600 dark:text-slate-300 border-slate-500/30',
};

const CARD_STYLES: Record<SubmissionStatus, string> = {
  pending: 'border-amber-500/30 hover:border-amber-500/50 bg-amber-500/5',
  approved: 'border-emerald-500/30 bg-emerald-500/5 opacity-80',
  rejected: 'border-red-500/30 bg-red-500/5 opacity-60',
  revoked: 'border-slate-500/30 bg-slate-500/5 opacity-60',
};

const STATUS_ICONS: Record<SubmissionStatus, React.ReactNode> = {
  pending: <Clock className="w-3.5 h-3.5" />,
  approved: <CheckCircle2 className="w-3.5 h-3.5" />,
  rejected: <XCircle className="w-3.5 h-3.5" />,
  revoked: <Undo2 className="w-3.5 h-3.5" />,
};

interface AdminApprovalViewProps {
  /** Lets the navbar's pending badge refresh once an item leaves the queue. */
  onQueueChange?: () => void;
}

export const AdminApprovalView: React.FC<AdminApprovalViewProps> = ({ onQueueChange }) => {
  const [items, setItems] = useState<PendingSubmission[]>([]);
  const [filterStatus, setFilterStatus] = useState<FilterStatus>('pending');
  const [isLoading, setIsLoading] = useState(false);
  const [processingId, setProcessingId] = useState<number | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editForm, setEditForm] = useState<{ content: string; source_id: string }>({ content: '', source_id: '' });

  const load = async (status: FilterStatus = filterStatus) => {
    setIsLoading(true);
    try {
      const data = await fetchPendingSubmissions(status);
      setItems(data);
    } catch (e) {
      console.error('Failed to load submissions:', e);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    load(filterStatus);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterStatus]);

  const handleStartEdit = (item: PendingSubmission) => {
    setEditingId(item.id);
    setEditForm({ content: item.content, source_id: item.source_id });
  };

  const handleSaveEdit = async (item: PendingSubmission) => {
    setProcessingId(item.id);
    try {
      await updateSubmission(item.id, editForm.content, editForm.source_id);
      setEditingId(null);
      await load();
    } catch (e: any) {
      alert(e.message || 'Failed to save');
    } finally {
      setProcessingId(null);
    }
  };

  const handleApprove = async (item: PendingSubmission) => {
    setProcessingId(item.id);
    try {
      if (editingId === item.id) {
        await updateSubmission(item.id, editForm.content, editForm.source_id);
      }
      await approveSubmission(item.id);
      setEditingId(null);
      await load();
      // Approving vectorizes the content, so both the pending badge and the
      // chunk/document counters move.
      onQueueChange?.();
    } catch (e: any) {
      alert(e.message || 'Failed to approve');
    } finally {
      setProcessingId(null);
    }
  };

  const handleRevoke = async (item: PendingSubmission) => {
    // Destructive and not undoable from this screen (re-adding means
    // resubmitting), so it asks rather than acting on a single click.
    if (!confirm(
      'Remove this approved content from the knowledge base?\n\n' +
      'The assistant will stop using it in answers. ' +
      'If it was a correction, the entry it replaced becomes active again.'
    )) return;

    setProcessingId(item.id);
    try {
      const result = await revokeSubmission(item.id);
      await load();
      onQueueChange?.();
      if (result.chunks_deleted === 0) {
        alert('No indexed content was found for this submission - it may already have been removed.');
      }
    } catch (e: any) {
      alert(e.message || 'Failed to revoke');
    } finally {
      setProcessingId(null);
    }
  };

  const handleReject = async (item: PendingSubmission) => {
    setProcessingId(item.id);
    try {
      await rejectSubmission(item.id);
      await load();
      onQueueChange?.();
    } catch (e: any) {
      alert(e.message || 'Failed to reject');
    } finally {
      setProcessingId(null);
    }
  };

  const pendingCount = items.filter((i) => i.status === 'pending').length;

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6 animate-in fade-in duration-200">

      <div className="glass rounded-3xl p-6 shadow-2xl flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div className="flex items-center space-x-3">
          <div className="p-2.5 bg-accent-600/20 border border-accent-500/30 rounded-2xl text-accent-500 dark:text-accent-400 shadow-md">
            <ShieldCheck className="w-6 h-6" />
          </div>
          <div>
            <h1 className="text-lg font-extrabold text-[var(--text)] tracking-tight">Admin Approval Queue</h1>
            <p className="text-xs text-[var(--text-secondary)]">
              Facts submitted through chat are never added automatically - review, edit, reject, or approve to vectorize.
            </p>
          </div>
        </div>

        <button
          onClick={() => load()}
          className="flex items-center space-x-1.5 text-xs font-bold text-[var(--text-secondary)] hover:text-[var(--text)] glass-well hover:bg-[var(--bg-inset)]/70 px-4 py-2.5 rounded-2xl transition-all cursor-pointer shrink-0"
        >
          <RefreshCw className={`w-3.5 h-3.5 text-accent-500 dark:text-accent-400 ${isLoading ? 'animate-spin' : ''}`} />
          <span>Refresh</span>
        </button>
      </div>

      <div className="flex items-center glass p-2 rounded-2xl shadow-xl">
        <div className="flex flex-wrap items-center gap-1.5 text-xs">
          {(['pending', 'approved', 'rejected', 'revoked', 'all'] as FilterStatus[]).map((status) => (
            <button
              key={status}
              onClick={() => setFilterStatus(status)}
              className={`px-4 py-2 rounded-xl font-bold transition-all cursor-pointer flex items-center space-x-2 capitalize ${
                filterStatus === status
                  ? 'bg-accent-600/20 text-accent-600 dark:text-accent-300 border border-accent-500/40 font-extrabold shadow-sm'
                  : 'text-[var(--text-muted)] hover:text-[var(--text)] hover:bg-[var(--bg-inset)]'
              }`}
            >
              {status === 'all' ? <Filter className="w-3.5 h-3.5" /> : STATUS_ICONS[status]}
              <span>{status}{status === 'pending' && pendingCount > 0 ? ` (${pendingCount})` : ''}</span>
            </button>
          ))}
        </div>
      </div>

      {items.length === 0 ? (
        <div className="glass rounded-2xl p-12 text-center text-[var(--text-muted)] space-y-3">
          <ShieldCheck className="w-10 h-10 text-[var(--text-faint)] mx-auto" />
          <p className="text-sm font-medium">
            {isLoading ? 'Loading...' : 'No submissions found for this filter.'}
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {items.map((item) => (
            <div
              key={item.id}
              className={`bg-[var(--bg-subtle)] border rounded-2xl p-5 space-y-4 transition-all backdrop-blur-md ${
                editingId === item.id
                  ? 'border-accent-500/50 bg-accent-500/5 shadow-lg shadow-accent-500/10'
                  : CARD_STYLES[item.status]
              }`}
            >
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border)] pb-3">
                <div className="flex items-center space-x-2 text-xs">
                  <span className="bg-accent-500/20 text-accent-600 dark:text-accent-300 border border-accent-400/30 px-2.5 py-0.5 rounded-full font-semibold">
                    {item.submission_type}
                  </span>
                  <span className="text-[var(--text-muted)] font-mono text-[10px]">source: {item.source_id}</span>
                  <span className="text-[var(--text-faint)] font-mono text-[10px]">
                    {new Date(item.created_at).toLocaleString('en-US')}
                  </span>
                </div>

                <span
                  className={`text-[11px] font-bold px-3 py-1 rounded-full flex items-center space-x-1 border ${STATUS_STYLES[item.status]}`}
                >
                  {STATUS_ICONS[item.status]}
                  <span className="capitalize">{item.status}</span>
                </span>
              </div>

              {editingId === item.id ? (
                <div className="space-y-3 glass-well p-4 rounded-xl border-accent-500/40">
                  <div className="space-y-1">
                    <label className="font-semibold text-[var(--text-secondary)] text-xs">Source id</label>
                    <input
                      type="text"
                      value={editForm.source_id}
                      onChange={(e) => setEditForm((prev) => ({ ...prev, source_id: e.target.value }))}
                      className="w-full bg-[var(--bg)] border border-[var(--border-strong)] rounded-xl p-2.5 text-[var(--text)] focus:outline-none focus:border-accent-500 font-mono text-xs"
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="font-semibold text-[var(--text-secondary)] text-xs">Content</label>
                    <textarea
                      rows={4}
                      value={editForm.content}
                      onChange={(e) => setEditForm((prev) => ({ ...prev, content: e.target.value }))}
                      className="w-full bg-[var(--bg)] border border-[var(--border-strong)] rounded-xl p-3 text-[var(--text)] font-mono text-xs focus:outline-none focus:border-accent-500 leading-relaxed"
                    />
                  </div>
                  <div className="flex flex-wrap items-center justify-end gap-2 pt-2 border-t border-[var(--border)]">
                    <button
                      onClick={() => setEditingId(null)}
                      disabled={processingId === item.id}
                      className="px-3.5 py-2 bg-[var(--bg-inset)] hover:bg-[var(--bg-inset)]/70 text-[var(--text-secondary)] rounded-xl text-xs font-semibold transition-all cursor-pointer flex items-center space-x-1.5"
                    >
                      <X className="w-3.5 h-3.5" /><span>Cancel</span>
                    </button>
                    <button
                      onClick={() => handleSaveEdit(item)}
                      disabled={processingId === item.id}
                      className="px-4 py-2 bg-accent-600/30 hover:bg-accent-600/50 text-accent-700 dark:text-accent-200 border border-accent-400/40 rounded-xl text-xs font-semibold transition-all cursor-pointer flex items-center space-x-1.5"
                    >
                      <Save className="w-3.5 h-3.5" /><span>Save Changes</span>
                    </button>
                    {item.status === 'pending' && (
                      <button
                        onClick={() => handleApprove(item)}
                        disabled={processingId === item.id}
                        className="px-4.5 py-2 bg-emerald-600 hover:bg-emerald-500 text-white border border-emerald-400/40 rounded-xl text-xs font-bold shadow-lg shadow-emerald-600/20 transition-all cursor-pointer flex items-center space-x-1.5"
                      >
                        <CheckCircle2 className="w-4 h-4" /><span>Save &amp; Approve</span>
                      </button>
                    )}
                  </div>
                </div>
              ) : (
                <div className="space-y-4">
                  <InjectionWarning markers={item.injection_markers} />

                  <div className="glass-well p-4 rounded-xl font-mono text-xs text-[var(--text-secondary)] leading-relaxed whitespace-pre-wrap">
                    {item.content}
                  </div>

                  {/* Approval is otherwise irreversible: the content is live in
                      the corpus and no other screen can reach a submission's
                      chunk. */}
                  {item.status === 'approved' && (
                    <div className="flex flex-wrap items-center justify-between gap-2 pt-3 border-t border-[var(--border)]">
                      <span className="text-[11px] text-[var(--text-muted)]">
                        Live in the knowledge base and usable in answers.
                      </span>
                      <button
                        onClick={() => handleRevoke(item)}
                        disabled={processingId === item.id}
                        className="px-4 py-2 bg-rose-500/20 hover:bg-rose-500/30 text-rose-600 dark:text-rose-300 border border-rose-500/40 rounded-xl text-xs font-semibold transition-all cursor-pointer flex items-center space-x-1.5 disabled:opacity-50"
                      >
                        <Undo2 className="w-4 h-4" />
                        <span>{processingId === item.id ? 'Removing...' : 'Remove from Knowledge Base'}</span>
                      </button>
                    </div>
                  )}

                  {item.status === 'revoked' && (
                    <p className="text-[11px] text-[var(--text-muted)] pt-3 border-t border-[var(--border)]">
                      Removed from the knowledge base - no longer used in answers.
                      Re-adding it means submitting the fact again.
                    </p>
                  )}

                  {item.status === 'pending' && (
                    <div className="flex flex-wrap items-center justify-end gap-2 pt-3 border-t border-[var(--border)]">
                      <button
                        onClick={() => handleStartEdit(item)}
                        disabled={processingId === item.id}
                        className="px-3.5 py-2 bg-accent-500/20 hover:bg-accent-500/30 text-accent-600 dark:text-accent-300 border border-accent-500/40 rounded-xl text-xs font-semibold transition-all cursor-pointer flex items-center space-x-1.5"
                      >
                        <Pencil className="w-3.5 h-3.5" /><span>Edit</span>
                      </button>
                      <button
                        onClick={() => handleReject(item)}
                        disabled={processingId === item.id}
                        className="px-4 py-2 bg-rose-500/20 hover:bg-rose-500/30 text-rose-600 dark:text-rose-300 border border-rose-500/40 rounded-xl text-xs font-semibold transition-all cursor-pointer flex items-center space-x-1.5"
                      >
                        <XCircle className="w-4 h-4" /><span>Reject</span>
                      </button>
                      <button
                        onClick={() => handleApprove(item)}
                        disabled={processingId === item.id}
                        className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white border border-emerald-400/40 rounded-xl text-xs font-bold shadow-lg shadow-emerald-600/20 transition-all cursor-pointer flex items-center space-x-1.5"
                      >
                        <CheckCircle2 className="w-4 h-4" /><span>Approve &amp; Vectorize</span>
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
