import React, { useEffect, useState } from 'react';
import { Check } from 'lucide-react';
import { useI18n } from '../../i18n';

// The stages graph/progress.py reports, in pipeline order.
const STAGES = ['understanding', 'searching', 'ranking', 'writing'].map((id) => ({ id }));

interface ProgressStepsProps {
  /** Stages reported so far, in arrival order. */
  stages: string[];
  startedAt: number;
}

/* What an answer is waiting on. Every step marked done or active is one the
   backend actually reported - nothing is timed or simulated. Steps not yet
   reached are listed too, dimmed, so the reader knows how much is left; a
   structured lookup that skips document search jumps straight past them.
   The running seconds sit on the active step: an answer takes 20-30
   seconds, and with nothing moving a reader can't tell slow from stuck. */
export const ProgressSteps: React.FC<ProgressStepsProps> = ({ stages, startedAt }) => {
  const [now, setNow] = useState(() => Date.now());
  const { t } = useI18n();

  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);

  const latest = stages[stages.length - 1];
  const activeIndex = latest ? STAGES.findIndex((s) => s.id === latest) : -1;
  const elapsed = Math.max(0, Math.floor((now - startedAt) / 1000));
  const progress = ((activeIndex + 1) / STAGES.length) * 100;

  return (
    <div role="status" aria-live="polite" aria-label={t.answerProgress}>
      <div className="h-[3px] bg-accent-100 dark:bg-accent-500/15">
        <div
          className="h-full bg-accent-600 dark:bg-accent-400 transition-[width] duration-500 ease-out"
          style={{ width: `${Math.max(progress, 6)}%` }}
        />
      </div>
      <ol className="px-4 sm:px-5 py-4 space-y-2.5">
        {STAGES.map((stage, idx) => {
          // Only stages the backend reported count as done; one it jumped
          // past (a structured lookup skips document search) shows as skipped.
          const done = idx < activeIndex && stages.includes(stage.id);
          const skipped = idx < activeIndex && !done;
          const active = idx === activeIndex || (activeIndex === -1 && idx === 0);
          return (
            <li
              key={stage.id}
              className={`flex items-center gap-3 text-[14px] ${
                active ? 'text-[var(--text)] font-medium' : done ? 'text-[var(--text-muted)]' : 'text-[var(--text-faint)]'
              }`}
            >
              <span
                className={`w-5 h-5 shrink-0 rounded-full flex items-center justify-center ${
                  done
                    ? 'bg-emerald-600 text-white dark:bg-emerald-500'
                    : active
                      ? 'border-2 border-accent-600 border-t-transparent animate-spin dark:border-accent-400 dark:border-t-transparent'
                      : 'border-[1.5px] border-[var(--border-strong)]'
                }`}
              >
                {done && <Check className="w-3 h-3" strokeWidth={3} />}
              </span>
              <span className={`min-w-0 ${skipped ? 'line-through decoration-[var(--border-strong)]' : ''}`}>{t.stages[stage.id]}</span>
              {active && (
                <span className="ml-auto font-mono text-[12px] font-normal tabular-nums text-[var(--text-muted)]">{elapsed}s</span>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
};
