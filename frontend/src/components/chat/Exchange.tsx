import React, { useMemo } from 'react';
import { Check, Clock, Copy, FileWarning, Flag, PenLine, ThumbsDown, ThumbsUp, Zap } from 'lucide-react';
import { ChatQueryResult, RetrievalDiagnostic } from '../../types';
import { AnswerBody } from './AnswerBody';
import { ProgressSteps } from './ProgressSteps';
import { InlineSources } from './Sources';
import { citationCounts } from './citations';
import { formatElapsed } from './content';
import { DOMAIN_TONE, domainById, domainForSources } from '../../config/programme';

export interface ChatMessage {
  id: string;
  sender: 'user' | 'assistant';
  text: string;
  timestamp: string;
  resultData?: ChatQueryResult;
}

interface ExchangeProps {
  question: ChatMessage;
  answer?: ChatMessage;
  /** This is the question currently being answered. */
  isPending: boolean;
  stages: string[];
  startedAt: number;
  isSelected: boolean;
  /** Sources go under the answer only when the evidence panel isn't shown. */
  showInlineSources: boolean;
  activeCitation: number | null;
  isAdmin: boolean;
  isCopied: boolean;
  rating?: 1 | -1;
  onSelect: () => void;
  onCitation: (n: number, item: RetrievalDiagnostic) => void;
  onOpenPassage: (item: RetrievalDiagnostic) => void;
  onCopy: () => void;
  onRate: (logId: number, rating: 1 | -1) => void;
  onSuggestCorrection: () => void;
}

const metaChip =
  'inline-flex items-center gap-1 h-6 px-2 rounded bg-[var(--bg-subtle)] border border-[var(--border)] font-mono text-[11px] text-[var(--text-muted)]';

const action =
  'inline-flex items-center justify-center gap-1.5 h-8 min-w-8 px-2 rounded-md text-[13px] text-[var(--text-secondary)] hover:text-[var(--text)] hover:bg-[var(--bg-inset)] transition-colors cursor-pointer';

/* One question and its answer as a single card: the question as its
   header, then live progress or the answer, its sources and the actions.
   Selecting a card shows its evidence in the side panel on wide screens. */
export const Exchange: React.FC<ExchangeProps> = ({
  question,
  answer,
  isPending,
  stages,
  startedAt,
  isSelected,
  showInlineSources,
  activeCitation,
  isAdmin,
  isCopied,
  rating,
  onSelect,
  onCitation,
  onOpenPassage,
  onCopy,
  onRate,
  onSuggestCorrection,
}) => {
  const result = answer?.resultData;
  const retrieval = result?.retrieval ?? [];
  const counts = useMemo(() => citationCounts(answer?.text ?? ''), [answer?.text]);
  const hasAnswerText = Boolean(answer && answer.text.length > 0);
  const domain = result ? domainById(domainForSources(retrieval.map((r) => r.source_id))) : null;

  const meta = (
    <>
      {domain && (
        <span className={`inline-flex items-center h-[22px] px-2 rounded-full border text-[11.5px] font-medium ${DOMAIN_TONE[domain.id].badge}`}>
          {domain.label}
        </span>
      )}
      <span className="font-mono text-[11.5px] text-[var(--text-faint)]">{question.timestamp}</span>
    </>
  );

  return (
    <article
      onClick={onSelect}
      aria-label={question.text}
      className={`bg-[var(--bg-elevated)] rounded-lg border overflow-hidden animate-msg-enter transition-shadow ${
        isSelected
          ? 'border-accent-600 ring-3 ring-accent-500/15 dark:border-accent-400'
          : 'border-[var(--border)] shadow-[var(--shadow-sm)]'
      }`}
    >
      <header className="flex items-start gap-3 px-4 sm:px-5 py-3.5 bg-[var(--bg-subtle)] border-b border-[var(--border)]">
        <span className="w-7 h-7 shrink-0 rounded-full bg-[var(--bg-inset)] text-[var(--text-secondary)] flex items-center justify-center text-[11px] font-semibold" aria-hidden="true">
          You
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="text-[15.5px] font-semibold leading-snug text-[var(--text)] pt-[3px] whitespace-pre-wrap break-words">
            <span className="sr-only">You asked: </span>
            {question.text}
          </h2>
          <div className="flex sm:hidden items-center gap-2 mt-1.5">{meta}</div>
        </div>
        <div className="hidden sm:flex items-center gap-2 shrink-0 pt-[3px]">{meta}</div>
      </header>

      {hasAnswerText ? (
        <div className="px-4 sm:px-5 py-4">
          {result?.hasExpiredDeadline && (
            <div className="mb-3 flex items-center gap-2 text-[13px] font-medium text-amber-800 dark:text-amber-300 bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/30 rounded-md px-3 py-2">
              <FileWarning className="w-4 h-4 shrink-0" />
              Mentions a deadline that has already passed
            </div>
          )}
          <AnswerBody
            text={answer!.text}
            retrieval={retrieval}
            activeCitation={isSelected ? activeCitation : null}
            onCitation={onCitation}
          />
        </div>
      ) : (
        isPending && <ProgressSteps stages={stages} startedAt={startedAt} />
      )}

      {result && showInlineSources && (
        <InlineSources retrieval={retrieval} counts={counts} onOpenPassage={onOpenPassage} />
      )}

      {result && (
        <footer
          className="flex flex-wrap items-center gap-x-1 gap-y-1.5 px-3 sm:px-4 py-2 border-t border-[var(--border)]"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex flex-wrap items-center gap-1.5 mr-auto pl-1">
            {result.elapsedMs > 0 && (
              <span className={metaChip} title={`This answer took ${(result.elapsedMs / 1000).toFixed(1)} seconds`}>
                <Clock className="w-3 h-3" />
                {formatElapsed(result.elapsedMs)}
                {retrieval.length > 0 && <span>· {retrieval.length} sources</span>}
              </span>
            )}
            {/* Admin-only: internal stage timings and the cache flag mean
                nothing to a student. */}
            {isAdmin && Object.entries(result.nodeLatencies || {}).map(([node, ms]) => (
              <span key={node} className={metaChip}>
                <Zap className="w-3 h-3 text-emerald-600 dark:text-emerald-400" />
                {node}: {Math.round(ms)}ms
              </span>
            ))}
            {isAdmin && result.cached && <span className={`${metaChip} !text-accent-700 dark:!text-accent-300`}>cached</span>}
            {result.autoFlaggedContribution && (
              <span className={`${metaChip} !text-amber-800 dark:!text-amber-300 !bg-amber-50 dark:!bg-amber-500/10`}>
                <Flag className="w-3 h-3" />
                Flagged: {result.autoFlaggedContribution}
              </span>
            )}
          </div>

          <div className="flex items-center">
            {result.queryLogId != null && (
              <>
                <button
                  onClick={() => onRate(result.queryLogId!, 1)}
                  aria-label="This answer was helpful"
                  title="This answer was helpful"
                  aria-pressed={rating === 1}
                  className={`${action} ${rating === 1 ? '!text-emerald-700 dark:!text-emerald-400 bg-emerald-50 dark:bg-emerald-500/10' : ''}`}
                >
                  <ThumbsUp className="w-4 h-4" />
                  <span className="hidden sm:inline">Helpful</span>
                </button>
                <button
                  onClick={() => onRate(result.queryLogId!, -1)}
                  aria-label="This answer was wrong or unhelpful"
                  title="This answer was wrong or unhelpful"
                  aria-pressed={rating === -1}
                  className={`${action} ${rating === -1 ? '!text-rose-700 dark:!text-rose-400 bg-rose-50 dark:bg-rose-500/10' : ''}`}
                >
                  <ThumbsDown className="w-4 h-4" />
                </button>
              </>
            )}
            <button onClick={onCopy} aria-label="Copy answer" title="Copy answer" className={action}>
              {isCopied ? (
                <>
                  <Check className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                  <span className="text-emerald-700 dark:text-emerald-400">Copied</span>
                </>
              ) : (
                <>
                  <Copy className="w-4 h-4" />
                  <span className="hidden sm:inline">Copy</span>
                </>
              )}
            </button>
            <button onClick={onSuggestCorrection} title="Something wrong or outdated? Suggest a correction" className={action}>
              <PenLine className="w-4 h-4" />
              <span>Suggest a correction</span>
            </button>
          </div>
        </footer>
      )}
    </article>
  );
};
