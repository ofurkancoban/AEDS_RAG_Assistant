import React, { useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import ReactMarkdown, { Components } from 'react-markdown';
// gfm: the system prompt invites tables when a fact varies by category.
import remarkGfm from 'remark-gfm';
import { FileWarning } from 'lucide-react';
import { RetrievalDiagnostic } from '../../types';
import { ANSWER_MARKDOWN_COMPONENTS } from '../markdown';
import { CITE_PREFIX, describeSource, linkifyCitations, plainSnippet, relevance } from './citations';
import { useI18n } from '../../i18n';

interface AnswerBodyProps {
  text: string;
  /** Passage [n] is retrieval[n-1]. Empty while the answer is still
      streaming - the chips show their numbers but only open once it lands. */
  retrieval: RetrievalDiagnostic[];
  /** The citation currently highlighted in the evidence panel, if any. */
  activeCitation?: number | null;
  onCitation: (n: number, item: RetrievalDiagnostic) => void;
}

const canHover = () => typeof window !== 'undefined' && window.matchMedia('(hover: hover)').matches;

const CitationChip: React.FC<{
  n: number;
  item?: RetrievalDiagnostic;
  isActive: boolean;
  onOpen: (n: number, item: RetrievalDiagnostic) => void;
}> = ({ n, item, isActive, onOpen }) => {
  const ref = useRef<HTMLButtonElement>(null);
  const { lang, t } = useI18n();
  const [pos, setPos] = useState<{ left: number; top: number; below: boolean } | null>(null);

  const show = () => {
    if (!item || !canHover() || !ref.current) return;
    const r = ref.current.getBoundingClientRect();
    const width = 320;
    const left = Math.min(Math.max(8, r.left + r.width / 2 - width / 2), window.innerWidth - width - 8);
    // Flip below the chip when there isn't room above it.
    const below = r.top < 220;
    setPos({ left, top: below ? r.bottom + 8 : r.top - 8, below });
  };

  const source = item ? describeSource(item.source_id, lang) : null;

  return (
    <>
      <button
        ref={ref}
        type="button"
        onMouseEnter={show}
        onMouseLeave={() => setPos(null)}
        onFocus={show}
        onBlur={() => setPos(null)}
        onClick={(e) => {
          e.stopPropagation();
          if (item) onOpen(n, item);
        }}
        disabled={!item}
        aria-label={source ? `${t.sourceN(n)}: ${source.title}` : t.sourceN(n)}
        className={`citation-chip ${isActive ? 'is-active' : ''}`}
      >
        {n}
      </button>
      {pos && item && source &&
        createPortal(
          <div
            role="tooltip"
            className="fixed z-[80] w-[320px] rounded-xl border border-[var(--border)] bg-[var(--bg-elevated)] shadow-[var(--shadow-lg)] p-3.5 pointer-events-none animate-in"
            style={{ left: pos.left, top: pos.top, transform: pos.below ? undefined : 'translateY(-100%)' }}
          >
            <div className="flex items-baseline justify-between gap-3">
              <span className="text-[13px] font-semibold text-[var(--text)] leading-snug">{source.title}</span>
              <span className="font-mono text-[10.5px] text-[var(--text-muted)] shrink-0">[{n}]</span>
            </div>
            <div className="mt-0.5 flex items-center gap-2 text-[11px] text-[var(--text-muted)]">
              <span>{source.kind}</span>
              {item.rerank_score != null && (
                <>
                  <span className="text-[var(--text-faint)]">·</span>
                  <span className="font-mono">{t.relevance} {Math.round(relevance(item.rerank_score) * 100)}%</span>
                </>
              )}
            </div>
            {item.expired_since && (
              <div className="mt-2 flex items-center gap-1.5 text-[11.5px] font-medium text-amber-700 dark:text-amber-400">
                <FileWarning className="w-3.5 h-3.5" /> {t.outdatedSince(item.expired_since)}
              </div>
            )}
            <p className="mt-2 pl-2.5 border-l-2 border-brass-400 text-[13.5px] leading-snug text-[var(--text-secondary)] line-clamp-5 whitespace-pre-line">
              {plainSnippet(item.snippet)}
            </p>
            <p className="mt-2 text-[11px] text-[var(--text-faint)]">{t.clickToShow}</p>
          </div>,
          document.body
        )}
    </>
  );
};

export const AnswerBody: React.FC<AnswerBodyProps> = ({ text, retrieval, activeCitation, onCitation }) => {
  const components = useMemo<Components>(
    () => ({
      ...ANSWER_MARKDOWN_COMPONENTS,
      a: (props) => {
        const href = props.href ?? '';
        if (href.startsWith(CITE_PREFIX)) {
          const n = Number(href.slice(CITE_PREFIX.length));
          return <CitationChip n={n} item={retrieval[n - 1]} isActive={activeCitation === n} onOpen={onCitation} />;
        }
        const Anchor = ANSWER_MARKDOWN_COMPONENTS.a as React.ComponentType<typeof props>;
        return <Anchor {...props} />;
      },
    }),
    [retrieval, activeCitation, onCitation]
  );

  return (
    <div className="answer-prose text-[15.5px] text-[var(--text-secondary)] break-words">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {linkifyCitations(text)}
      </ReactMarkdown>
    </div>
  );
};
