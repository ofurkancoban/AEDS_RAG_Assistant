import React from 'react';
import { BookOpen, CheckCircle2, FileWarning, Loader2, PenLine } from 'lucide-react';
import { RetrievalDiagnostic } from '../../types';
import { Modal } from '../Modal';
import { describeSource, plainSnippet } from './citations';
import { useI18n } from '../../i18n';

export const ChunkDetailModal: React.FC<{
  chunk: RetrievalDiagnostic | null;
  onClose: () => void;
}> = ({ chunk, onClose }) => {
  const { lang, t } = useI18n();
  const source = chunk ? describeSource(chunk.source_id, lang) : null;
  return (
  <Modal
    isOpen={chunk !== null}
    onClose={onClose}
    eyebrow={source ? `${t.referencedPassage} · ${source.kind}` : ''}
    title={source ? source.title : ''}
    icon={<BookOpen className="w-4 h-4" />}
    maxWidth="sm:max-w-2xl"
  >
    {chunk && (
      <div className="space-y-4">
        <p className="-mt-1 font-mono text-[11.5px] text-[var(--text-muted)] break-all">{chunk.source_id}</p>
        {chunk.expired_since && (
          <div className="flex items-start gap-2 text-[13px] font-medium text-amber-800 dark:text-amber-300 bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-900/60 rounded-lg p-3">
            <FileWarning className="w-4 h-4 mt-px shrink-0" />
            <span>{t.pastCycle(chunk.expired_since)}</span>
          </div>
        )}

        {(chunk.rerank_score != null || chunk.hybrid_score != null) && (
          <dl className="grid grid-cols-2 gap-2">
            {chunk.rerank_score != null && (
              <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)] px-3 py-2">
                <dt className="eyebrow">{t.rerankScore}</dt>
                <dd className="font-mono text-[15px] text-emerald-700 dark:text-emerald-400">{chunk.rerank_score.toFixed(3)}</dd>
              </div>
            )}
            {chunk.hybrid_score != null && (
              <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)] px-3 py-2">
                <dt className="eyebrow">{t.hybridScore}</dt>
                <dd className="font-mono text-[15px] text-accent-700 dark:text-accent-300">{chunk.hybrid_score.toFixed(4)}</dd>
              </div>
            )}
          </dl>
        )}

        <figure className="space-y-1.5">
          <figcaption className="eyebrow">{t.excerpt}</figcaption>
          <blockquote className="max-h-72 overflow-y-auto whitespace-pre-wrap rounded-lg border-l-[3px] border-brass-400 bg-[var(--bg-subtle)] px-4 py-3 text-[15px] leading-relaxed text-[var(--text-secondary)]">
            {plainSnippet(chunk.snippet)}
          </blockquote>
        </figure>
      </div>
    )}
  </Modal>
  );
};

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
}) => {
  const { t } = useI18n();
  return (
  <Modal
    isOpen={isOpen}
    onClose={onClose}
    eyebrow={t.reviewQueue}
    title={t.suggestCorrection}
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
          {t.suggestIntro}
        </p>

        <fieldset className="space-y-1.5">
          <legend className="text-[13px] font-medium text-[var(--text-secondary)] mb-1.5">{t.type}</legend>
          <div className="grid grid-cols-2 gap-2">
            {([
              ['new_info', t.newInformation],
              ['correction', t.correction],
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
          <span className="text-[13px] font-medium text-[var(--text-secondary)]">{t.relatedDocument}</span>
          <input
            type="text"
            value={sourceId}
            onChange={(e) => onSourceIdChange(e.target.value)}
            placeholder={t.relatedPlaceholder}
            className={inputClass}
          />
        </label>

        <label className="block space-y-1.5">
          <span className="text-[13px] font-medium text-[var(--text-secondary)]">{t.whatToKnow}</span>
          <textarea
            rows={4}
            value={content}
            onChange={(e) => onContentChange(e.target.value)}
            placeholder={t.whatToKnowPlaceholder}
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
            {t.cancel}
          </button>
          <button
            type="submit"
            disabled={isSubmitting}
            className="h-10 px-5 flex items-center justify-center gap-2 rounded-lg bg-accent-700 hover:bg-accent-600 dark:bg-accent-600 dark:hover:bg-accent-500 disabled:opacity-60 text-white text-[14px] font-medium shadow-sm transition-colors cursor-pointer"
          >
            {isSubmitting && <Loader2 className="w-4 h-4 animate-spin" />}
            {isSubmitting ? t.submitting : t.submitForReview}
          </button>
        </div>
      </form>
    )}
  </Modal>
  );
};
