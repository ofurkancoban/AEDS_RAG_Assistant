import React, { useEffect, useState } from 'react';
import { Check, MessagesSquare, ShieldAlert } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ANSWER_MARKDOWN_COMPONENTS } from './markdown';
import { AnswerCheck } from '../types';
import { listAnswerChecks, markAnswerCheckSeen } from '../api/client';

/* Answers the background statement check flagged, from any turn of any
   conversation (the review queue above only holds first answers), so a
   wrong follow-up answer is seen by someone. */
export const AnswerChecksList: React.FC<{ onCountChange?: (n: number) => void }> = ({ onCountChange }) => {
  const [items, setItems] = useState<AnswerCheck[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);

  const load = async () => {
    setIsLoading(true);
    try {
      const checks = await listAnswerChecks();
      setItems(checks);
      onCountChange?.(checks.length);
    } catch (e) {
      console.error('Failed to load answer checks:', e);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const markSeen = async (id: number) => {
    setBusyId(id);
    try {
      await markAnswerCheckSeen(id);
      await load();
    } finally {
      setBusyId(null);
    }
  };

  if (items.length === 0) {
    return (
      <div className="glass rounded-2xl p-12 text-center text-[var(--text-muted)] space-y-3">
        <MessagesSquare className="w-10 h-10 text-[var(--text-faint)] mx-auto" />
        <p className="text-sm font-medium">{isLoading ? 'Loading...' : 'No flagged answers in the last 30 days.'}</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {items.map((item) => (
        <div key={item.id} className="bg-[var(--bg-subtle)] border border-[var(--border)] rounded-2xl p-5 space-y-3">
          <div className="flex items-start justify-between gap-3">
            <h3 className="text-sm font-semibold text-[var(--text)]">{item.question}</h3>
            <span className="shrink-0 font-mono text-[11px] text-[var(--text-muted)]">
              {new Date(item.created_at + (item.created_at.endsWith('Z') ? '' : 'Z')).toLocaleString('en-GB')}
            </span>
          </div>
          <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-3 py-2 space-y-1">
            <p className="flex items-center gap-1.5 text-[12px] font-semibold text-rose-700 dark:text-rose-300">
              <ShieldAlert className="w-3.5 h-3.5" /> Not supported by the context
            </p>
            <ul className="list-disc pl-5 text-[12px] text-rose-800 dark:text-rose-200 space-y-0.5">
              {item.findings.map((f, i) => (
                <li key={i}>{f}</li>
              ))}
            </ul>
          </div>
          <div className="prose-sm text-[13px] text-[var(--text-secondary)] max-h-64 overflow-y-auto">
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={ANSWER_MARKDOWN_COMPONENTS}>
              {item.answer}
            </ReactMarkdown>
          </div>
          <div className="flex justify-end">
            <button
              type="button"
              disabled={busyId === item.id}
              onClick={() => markSeen(item.id)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border border-[var(--border)] text-[var(--text-secondary)] hover:text-[var(--text)] hover:bg-[var(--bg-inset)] disabled:opacity-50 cursor-pointer"
            >
              <Check className="w-3.5 h-3.5" /> Mark as seen
            </button>
          </div>
        </div>
      ))}
    </div>
  );
};
