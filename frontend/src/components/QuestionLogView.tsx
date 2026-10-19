import React, { useEffect, useState } from 'react';
import { ChevronDown, ScrollText, Search, ShieldAlert, ShieldCheck, ThumbsDown, ThumbsUp } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ANSWER_MARKDOWN_COMPONENTS } from './markdown';
import { QuestionLogItem } from '../types';
import { getQuestionLog } from '../api/client';

/* Every question asked, with its answer. The answer review queue only
   holds answers that could be given to other students, so follow-ups,
   ECTS Tracker widget questions, canteen menus and small talk only show
   up here. A widget question is shown without the student's progress
   block. */

const PAGE = 50;

const select =
  'h-9 rounded-xl border border-[var(--border)] bg-[var(--bg)] px-3 text-xs text-[var(--text)] focus:outline-none focus:border-accent-500 cursor-pointer';

const chip = 'inline-flex items-center gap-1 h-5 px-1.5 rounded text-[10px] font-semibold border whitespace-nowrap';

const SOURCE_STYLE: Record<string, string> = {
  site: 'bg-sky-500/10 border-sky-500/30 text-sky-700 dark:text-sky-300',
  widget: 'bg-violet-500/10 border-violet-500/30 text-violet-700 dark:text-violet-300',
  telegram: 'bg-teal-500/10 border-teal-500/30 text-teal-700 dark:text-teal-300',
};

const Row: React.FC<{ item: QuestionLogItem }> = ({ item }) => {
  const [open, setOpen] = useState(false);
  const flagged = item.check_findings && item.check_findings.length > 0;
  const when = new Date(item.created_at + (item.created_at.endsWith('Z') ? '' : 'Z')).toLocaleString('en-GB', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
  return (
    <li className="border-b border-[var(--border)] last:border-b-0">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="w-full text-left px-4 py-3 hover:bg-[var(--bg-inset)] cursor-pointer"
      >
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="font-mono text-[11px] text-[var(--text-muted)] mr-1">{when}</span>
          <span className={`${chip} ${SOURCE_STYLE[item.source] ?? 'border-[var(--border)] text-[var(--text-muted)]'}`}>{item.source}</span>
          <span className={`${chip} border-[var(--border)] text-[var(--text-muted)]`} title="Position in the conversation">
            {item.turn}/{item.turns}
          </span>
          {!item.answered && (
            <span className={`${chip} bg-amber-500/10 border-amber-500/30 text-amber-700 dark:text-amber-300`}>not answered</span>
          )}
          {item.cached && <span className={`${chip} border-[var(--border)] text-[var(--text-muted)]`}>approved answer</span>}
          {item.rating === 1 && <ThumbsUp className="w-3.5 h-3.5 text-emerald-600" aria-label="Rated helpful" />}
          {item.rating === -1 && <ThumbsDown className="w-3.5 h-3.5 text-rose-600" aria-label="Rated unhelpful" />}
          {flagged && (
            <span className={`${chip} bg-rose-500/10 border-rose-500/30 text-rose-700 dark:text-rose-300`}>
              <ShieldAlert className="w-3 h-3" /> check: {item.check_findings!.length}
            </span>
          )}
          {item.check_findings && item.check_findings.length === 0 && (
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" aria-label="Automatic check found nothing unsupported" />
          )}
          <ChevronDown className={`ml-auto w-4 h-4 text-[var(--text-faint)] transition-transform ${open ? 'rotate-180' : ''}`} />
        </div>
        <p className="mt-1 text-sm font-medium text-[var(--text)] break-words">{item.question}</p>
      </button>
      {open && (
        <div className="px-4 pb-4 space-y-3">
          {flagged && (
            <ul className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-3 py-2 list-disc pl-7 text-[12px] text-rose-800 dark:text-rose-200 space-y-0.5">
              {item.check_findings!.map((f, i) => (
                <li key={i}>{f}</li>
              ))}
            </ul>
          )}
          <div className="rounded-xl border border-[var(--border)] bg-[var(--bg)] px-3 py-2 text-[13px] text-[var(--text-secondary)] max-h-80 overflow-y-auto">
            {item.answer ? (
              <ReactMarkdown remarkPlugins={[remarkGfm]} components={ANSWER_MARKDOWN_COMPONENTS}>
                {item.answer}
              </ReactMarkdown>
            ) : (
              <p className="italic text-[var(--text-muted)]">Answer no longer stored (conversations are kept 90 days).</p>
            )}
          </div>
          <p className="font-mono text-[11px] text-[var(--text-muted)]">
            {item.latency_ms ? `${(item.latency_ms / 1000).toFixed(1)}s` : ''}
            {item.source_ids.length > 0 && ` · ${item.source_ids.join(', ')}`}
          </p>
        </div>
      )}
    </li>
  );
};

export const QuestionLogView: React.FC = () => {
  const [days, setDays] = useState(7);
  const [source, setSource] = useState('all');
  const [show, setShow] = useState('all');
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [items, setItems] = useState<QuestionLogItem[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(false);

  const load = async (offset: number) => {
    setIsLoading(true);
    try {
      const page = await getQuestionLog({ days, source, show, search: query, offset, limit: PAGE });
      setItems((prev) => (offset === 0 ? page.items : [...prev, ...page.items]));
      setTotal(page.total);
    } catch (e) {
      console.error('Failed to load the question log:', e);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    load(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [days, source, show, query]);

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 py-8 space-y-4">
      <div className="flex items-center gap-3">
        <ScrollText className="w-6 h-6 text-accent-600" />
        <div>
          <h2 className="text-lg font-semibold text-[var(--text)]">Question Log</h2>
          <p className="text-xs text-[var(--text-muted)]">
            Every question with its answer: follow-ups, ECTS Tracker widget questions and canteen menus included. Widget
            questions are shown without the student's course list.
          </p>
        </div>
      </div>

      <form
        className="flex flex-wrap items-center gap-2 glass p-2 rounded-2xl"
        onSubmit={(e) => {
          e.preventDefault();
          setQuery(search.trim());
        }}
      >
        <select className={select} value={days} onChange={(e) => setDays(Number(e.target.value))} aria-label="Period">
          <option value={1}>Last 24 hours</option>
          <option value={7}>Last 7 days</option>
          <option value={30}>Last 30 days</option>
          <option value={90}>Last 90 days</option>
        </select>
        <select className={select} value={source} onChange={(e) => setSource(e.target.value)} aria-label="Asked from">
          <option value="all">All sources</option>
          <option value="site">Site</option>
          <option value="widget">ECTS Tracker widget</option>
          <option value="telegram">Telegram</option>
        </select>
        <select className={select} value={show} onChange={(e) => setShow(e.target.value)} aria-label="Show">
          <option value="all">All questions</option>
          <option value="flagged">Flagged by the check</option>
          <option value="unanswered">Not answered</option>
          <option value="downvoted">Rated unhelpful</option>
        </select>
        <div className="relative flex-1 min-w-[180px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[var(--text-faint)]" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search questions"
            className="h-9 w-full rounded-xl border border-[var(--border)] bg-[var(--bg)] pl-8 pr-3 text-xs text-[var(--text)] focus:outline-none focus:border-accent-500"
          />
        </div>
        <span className="text-xs text-[var(--text-muted)] px-2 tabular-nums">{total} questions</span>
      </form>

      {items.length === 0 ? (
        <div className="glass rounded-2xl p-12 text-center text-sm text-[var(--text-muted)]">
          {isLoading ? 'Loading...' : 'No questions for these filters.'}
        </div>
      ) : (
        <ul className="glass rounded-2xl overflow-hidden">
          {items.map((item) => (
            <Row key={item.id} item={item} />
          ))}
        </ul>
      )}

      {items.length < total && (
        <div className="flex justify-center">
          <button
            type="button"
            disabled={isLoading}
            onClick={() => load(items.length)}
            className="px-4 py-2 rounded-xl text-xs font-semibold border border-[var(--border)] text-[var(--text-secondary)] hover:bg-[var(--bg-inset)] disabled:opacity-50 cursor-pointer"
          >
            {isLoading ? 'Loading...' : `Show more (${total - items.length} left)`}
          </button>
        </div>
      )}
    </div>
  );
};
