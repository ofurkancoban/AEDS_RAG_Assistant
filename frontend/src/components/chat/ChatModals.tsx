import React from 'react';
import { BookOpen, CheckCircle2, FileWarning, Loader2, PenLine } from 'lucide-react';
import { RetrievalDiagnostic } from '../../types';
import { Modal } from '../Modal';
import { describeSource, plainSnippet } from './citations';

export const ChunkDetailModal: React.FC<{
  chunk: RetrievalDiagnostic | null;
  onClose: () => void;
}> = ({ chunk, onClose }) => (
  <Modal
    isOpen={chunk !== null}
    onClose={onClose}
    eyebrow={chunk ? `Referenced passage · ${describeSource(chunk.source_id).kind}` : ''}
    title={chunk ? describeSource(chunk.source_id).title : ''}
    icon={<BookOpen className="w-4 h-4" />}
    maxWidth="sm:max-w-2xl"
  >
    {chunk && (
      <div className="space-y-4">
        <p className="-mt-1 font-mono text-[11.5px] text-[var(--text-muted)] break-all">{chunk.source_id}</p>
        {chunk.expired_since && (
          <div className="flex items-start gap-2 text-[13px] font-medium text-amber-800 dark:text-amber-300 bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-900/60 rounded-lg p-3">
            <FileWarning className="w-4 h-4 mt-px shrink-0" />
            <span>This source describes a cycle that ended on {chunk.expired_since}. Any dates in it belong to a past cycle.</span>
          </div>
        )}

        {(chunk.rerank_score != null || chunk.hybrid_score != null) && (
          <dl className="grid grid-cols-2 gap-2">
            {chunk.rerank_score != null && (
              <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)] px-3 py-2">
                <dt className="eyebrow">Rerank score</dt>
                <dd className="font-mono text-[15px] text-emerald-700 dark:text-emerald-400">{chunk.rerank_score.toFixed(3)}</dd>
              </div>
            )}
            {chunk.hybrid_score != null && (
              <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)] px-3 py-2">
                <dt className="eyebrow">Hybrid score</dt>
                <dd className="font-mono text-[15px] text-accent-700 dark:text-accent-300">{chunk.hybrid_score.toFixed(4)}</dd>
              </div>
            )}
          </dl>
        )}

        <figure className="space-y-1.5">
          <figcaption className="eyebrow">Excerpt</figcaption>
          <blockquote className="max-h-72 overflow-y-auto whitespace-pre-wrap rounded-lg border-l-[3px] border-brass-400 bg-[var(--bg-subtle)] px-4 py-3 text-[15px] leading-relaxed text-[var(--text-secondary)]">
            {plainSnippet(chunk.snippet)}
          </blockquote>
        </figure>
      </div>
    )}
  </Modal>
);

interface SuggestKnowledgeModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (e: React.FormEvent) => void;
  type: 'new_info' | 'correction';
  onTypeChange: (type: 'new_info' | 'correction') => void;
  sourceId: string;
  onSourceIdChange: (value: string) => void;
  content: string;
  onContentChange: (value: string) => void;
  isSubmitting: boolean;
  successMessage: string | null;
}

const inputClass =
  'w-full rounded-lg bg-[var(--bg-subtle)] border border-[var(--border)] px-3 py-2.5 text-base sm:text-[14px] text-[var(--text)] placeholder:text-[var(--text-faint)] focus:outline-none focus:border-accent-500 focus:ring-3 focus:ring-accent-500/15 transition-all';

export const SuggestKnowledgeModal: React.FC<SuggestKnowledgeModalProps> = ({
  isOpen,
  onClose,
  onSubmit,
  type,
  onTypeChange,
  sourceId,
  onSourceIdChange,
  content,
  onContentChange,
  isSubmitting,
  successMessage,
}) => (
  <Modal
    isOpen={isOpen}
    onClose={onClose}
    eyebrow="Admin review queue"
    title="Suggest a correction"
    icon={<PenLine className="w-4 h-4" />}
  >
    {successMessage ? (
      <div className="flex items-center gap-3 rounded-lg border border-emerald-200 dark:border-emerald-900/60 bg-emerald-50 dark:bg-emerald-950/40 p-4 text-[14px] text-emerald-800 dark:text-emerald-300">
        <CheckCircle2 className="w-6 h-6 shrink-0" />
        <span>{successMessage}</span>
      </div>
    ) : (
      <form onSubmit={onSubmit} className="space-y-4">
        <p className="text-[13.5px] leading-relaxed text-[var(--text-secondary)]">
          Nothing you submit reaches the assistant's answers until the programme team has
          reviewed and approved it.
        </p>

        <fieldset className="space-y-1.5">
          <legend className="text-[13px] font-medium text-[var(--text-secondary)] mb-1.5">Type</legend>
          <div className="grid grid-cols-2 gap-2">
            {([
              ['new_info', 'New information'],
              ['correction', 'Correction'],
            ] as const).map(([value, label]) => (
              <button
                key={value}
                type="button"
                onClick={() => onTypeChange(value)}
                aria-pressed={type === value}
                className={`h-10 rounded-lg border text-[13.5px] font-medium transition-colors cursor-pointer ${
                  type === value
                    ? 'border-accent-500 bg-accent-50 dark:bg-accent-900/40 text-accent-800 dark:text-accent-200'
                    : 'border-[var(--border)] text-[var(--text-secondary)] hover:bg-[var(--bg-inset)]'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </fieldset>

        <label className="block space-y-1.5">
          <span className="text-[13px] font-medium text-[var(--text-secondary)]">Related document or topic</span>
          <input
            type="text"
            value={sourceId}
            onChange={(e) => onSourceIdChange(e.target.value)}
            placeholder="e.g. AEDS_website_exams_regulations"
            className={inputClass}
          />
        </label>

        <label className="block space-y-1.5">
          <span className="text-[13px] font-medium text-[var(--text-secondary)]">What should the assistant know?</span>
          <textarea
            rows={4}
            value={content}
            onChange={(e) => onContentChange(e.target.value)}
            placeholder="e.g. The Econometrics II resit exam takes place on Dec 12 at 14:00 in Room 402."
            className={`${inputClass} resize-y min-h-[110px]`}
            required
          />
        </label>

        <div className="flex flex-col-reverse sm:flex-row sm:justify-end gap-2 pt-1">
          <button
            type="button"
            onClick={onClose}
            className="h-10 px-4 rounded-lg border border-[var(--border)] text-[14px] font-medium text-[var(--text-secondary)] hover:bg-[var(--bg-inset)] transition-colors cursor-pointer"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={isSubmitting}
            className="h-10 px-5 flex items-center justify-center gap-2 rounded-lg bg-accent-700 hover:bg-accent-600 dark:bg-accent-600 dark:hover:bg-accent-500 disabled:opacity-60 text-white text-[14px] font-medium shadow-sm transition-colors cursor-pointer"
          >
            {isSubmitting && <Loader2 className="w-4 h-4 animate-spin" />}
            {isSubmitting ? 'Submitting...' : 'Submit for review'}
          </button>
        </div>
      </form>
    )}
  </Modal>
);
