import React, { useEffect, useRef } from 'react';
import { AlertTriangle, FileSearch, PenLine } from 'lucide-react';
import { RetrievalDiagnostic } from '../../types';
import { describeSource, plainSnippet, relevance } from './citations';
import { useI18n } from '../../i18n';

const RelevanceBar: React.FC<{ score: number | null | undefined; width?: string }> = ({ score, width = 'w-14' }) => {
  const { t } = useI18n();
  if (score == null) return null;
  const pct = Math.round(relevance(score) * 100);
  return (
    <span className="flex items-center gap-2 shrink-0" aria-label={t.relevanceLabel(pct)}>
      <span className={`${width} h-1 rounded-full bg-accent-100 dark:bg-accent-500/15 overflow-hidden`} aria-hidden="true">
        <span className="block h-full rounded-full bg-accent-600 dark:bg-accent-400" style={{ width: `${pct}%` }} />
      </span>
      <span className="w-8 text-right font-mono text-[11px] tabular-nums text-[var(--text-muted)]">{pct}%</span>
    </span>
  );
};

function formatDate(iso: string, locale: string): string {
  const d = new Date(`${iso}T00:00:00`);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString(locale, { day: 'numeric', month: 'short', year: 'numeric' });
}

const OutdatedTag: React.FC<{ since: string; long?: boolean }> = ({ since, long }) => {
  const { t } = useI18n();
  return (
  <span className="inline-flex items-center gap-1 px-1.5 py-px rounded text-[11px] font-medium text-amber-800 bg-amber-50 dark:text-amber-300 dark:bg-amber-500/15 shrink-0">
    <AlertTriangle className="w-3 h-3" />
    {long ? t.outdatedSince(formatDate(since, t.dateLocale)) : t.outdated}
  </span>
  );
};

interface SourcesProps {
  retrieval: RetrievalDiagnostic[];
  counts: Map<number, number>;
  onOpenPassage: (item: RetrievalDiagnostic) => void;
}

/* Under the answer, on screens without room for the evidence panel. */
export const InlineSources: React.FC<SourcesProps> = ({ retrieval, counts, onOpenPassage }) => {
  const { lang, t } = useI18n();
  if (retrieval.length === 0) return null;
  const anyCited = counts.size > 0;
  return (
    <section aria-label={t.sources} className="border-t border-[var(--border)] bg-[var(--bg-subtle)] px-4 sm:px-5 py-3">
      <h3 className="eyebrow !text-[var(--text)] mb-1">
        {t.sources}{anyCited && <span className="text-[var(--text-muted)] font-medium"> · {t.citedOf(counts.size, retrieval.length)}</span>}
      </h3>
      <ol>
        {retrieval.map((item, idx) => {
          const n = idx + 1;
          const cited = !anyCited || counts.has(n);
          const source = describeSource(item.source_id, lang);
          return (
            <li key={idx} className="border-t border-[var(--border)] first:border-t-0">
              <button
                onClick={() => onOpenPassage(item)}
                className={`w-full flex items-center gap-2.5 py-2 text-left cursor-pointer group ${cited ? '' : 'opacity-55'}`}
              >
                <span className="citation-chip !m-0 !text-[10.5px] shrink-0">{n}</span>
                <span className="min-w-0 flex-1 flex items-center gap-2">
                  <span className="truncate text-[13.5px] text-[var(--text)] group-hover:text-accent-700 dark:group-hover:text-accent-300">
                    {source.title}
                    <span className="text-[var(--text-muted)]"> · {source.kind}</span>
                  </span>
                  {item.expired_since && <OutdatedTag since={item.expired_since} />}
                </span>
                <RelevanceBar score={item.rerank_score} />
              </button>
            </li>
          );
        })}
      </ol>
    </section>
  );
};

interface EvidencePanelProps {
  question?: string;
  retrieval: RetrievalDiagnostic[];
  counts: Map<number, number>;
  activeCitation: number | null;
  onOpenPassage: (item: RetrievalDiagnostic) => void;
  onSuggestCorrection: () => void;
}

/* The selected answer's evidence, beside the conversation on wide screens:
   each passage with its quoted text, so checking an answer never means
   leaving it. A citation clicked in the answer highlights its passage here. */
export const EvidencePanel: React.FC<EvidencePanelProps> = ({
  question,
  retrieval,
  counts,
  activeCitation,
  onOpenPassage,
  onSuggestCorrection,
}) => {
  const itemRefs = useRef<(HTMLLIElement | null)[]>([]);
  const anyCited = counts.size > 0;
  const { lang, t } = useI18n();

  useEffect(() => {
    if (activeCitation == null) return;
    itemRefs.current[activeCitation - 1]?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, [activeCitation]);

  return (
    <aside className="hidden xl:flex w-[360px] shrink-0 flex-col bg-[var(--bg-elevated)] border-l border-[var(--border)]" aria-label={t.evidence}>
      <div className="px-5 py-3.5 border-b border-[var(--border)]">
        <h2 className="text-[14px] font-semibold text-[var(--text)]">{t.evidence}</h2>
        <p className="text-[12px] text-[var(--text-muted)] truncate">
          {question ? t.sourcesFor(question) : t.sourcesOfSelected}
        </p>
      </div>

      {retrieval.length === 0 ? (
        <div className="flex-1 flex flex-col items-center justify-center text-center px-8 text-[var(--text-muted)]">
          <FileSearch className="w-8 h-8 mb-3 text-[var(--text-faint)]" />
          <p className="text-[13.5px] font-medium text-[var(--text-secondary)]">
            {question ? t.noDocuments : t.sourcesAppear}
          </p>
          <p className="text-[12.5px] mt-1 leading-relaxed">
            {question ? t.noDocumentsBody : t.sourcesAppearBody}
          </p>
        </div>
      ) : (
        <ol className="flex-1 overflow-y-auto p-3 space-y-2.5">
          {retrieval.map((item, idx) => {
            const n = idx + 1;
            const times = counts.get(n) ?? 0;
            const cited = !anyCited || times > 0;
            const active = activeCitation === n;
            const source = describeSource(item.source_id, lang);
            return (
              <li key={idx} ref={(el) => { itemRefs.current[idx] = el; }}>
                <button
                  onClick={() => onOpenPassage(item)}
                  className={`w-full text-left rounded-lg border p-3 transition-colors cursor-pointer ${
                    active
                      ? 'border-accent-600 ring-3 ring-accent-500/15 dark:border-accent-400'
                      : 'border-[var(--border)] hover:border-[var(--border-strong)]'
                  } ${cited ? '' : 'opacity-55 hover:opacity-100'}`}
                >
                  <div className="flex items-center gap-2">
                    <span className={`citation-chip !m-0 !text-[10.5px] ${active ? 'is-active' : ''}`}>{n}</span>
                    <span className="text-[13.5px] font-semibold text-[var(--text)] truncate">{source.title}</span>
                    <span className="ml-auto"><RelevanceBar score={item.rerank_score} width="w-12" /></span>
                  </div>
                  <div className="mt-1 flex items-center gap-2 text-[12px] text-[var(--text-muted)]">
                    <span className="truncate">
                      {source.kind} · {anyCited ? (times > 0 ? t.citedTimes(times) : t.retrievedNotCited) : t.retrieved}
                    </span>
                  </div>
                  {item.expired_since && (
                    <div className="mt-1.5"><OutdatedTag since={item.expired_since} long /></div>
                  )}
                  {cited && (
                    <blockquote className="mt-2 px-2.5 py-2 rounded-r border-l-2 border-[var(--border-strong)] bg-[var(--bg-subtle)] text-[12.5px] leading-relaxed text-[var(--text-secondary)] line-clamp-6 whitespace-pre-line">
                      {plainSnippet(item.snippet)}
                    </blockquote>
                  )}
                </button>
              </li>
            );
          })}
        </ol>
      )}

      <div className="px-5 py-3 border-t border-[var(--border)] text-[12.5px] text-[var(--text-muted)]">
        {t.somethingWrong}{' '}
        <button onClick={onSuggestCorrection} className="inline-flex items-center gap-1 font-medium text-accent-700 dark:text-accent-300 hover:underline cursor-pointer">
          <PenLine className="w-3.5 h-3.5" />
          {t.suggestCorrection}
        </button>
      </div>
    </aside>
  );
};
