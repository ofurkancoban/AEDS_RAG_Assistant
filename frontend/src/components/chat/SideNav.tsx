import React, { useEffect, useState } from 'react';
import { ChevronDown, Plus, X } from 'lucide-react';
import type { ThreadSummary } from '../../api/client';
import { PROGRAMME, DOMAIN_TONE, localizedDomains } from '../../config/programme';
import { useI18n } from '../../i18n';
import { VersionBadge } from '../VersionBadge';
import { VisitorCounter } from '../VisitorCounter';

interface SideNavProps {
  isOpen: boolean;
  onClose: () => void;
  onNewQuestion: () => void;
  onAskTopic: (query: string) => void;
  isQuerying: boolean;
  /** The visitor's own earlier conversations, newest first. */
  threads: ThreadSummary[];
  activeThreadId: string | null;
  onOpenThread: (threadId: string) => void;
}

/* Topic navigation, filed by domain. A permanent column from lg up; below
   that a drawer opened from the header, so the conversation keeps the whole
   screen on a phone. */
// Long topic lists show this many until expanded, so every domain's heading
// stays within reach - on a phone the programme's list alone would otherwise
// push the other domains out of the drawer's first screen.
const COLLAPSED_COUNT = 6;
const RECENT_COLLAPSED_COUNT = 4;

export const SideNav: React.FC<SideNavProps> = ({
  isOpen,
  onClose,
  onNewQuestion,
  onAskTopic,
  isQuerying,
  threads,
  activeThreadId,
  onOpenThread,
}) => {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [showAllRecent, setShowAllRecent] = useState(false);
  const { lang, t } = useI18n();
  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isOpen, onClose]);

  return (
    <>
      <div
        className={`lg:hidden fixed inset-0 z-[55] bg-black/40 transition-opacity duration-200 ${
          isOpen ? 'opacity-100' : 'opacity-0 pointer-events-none'
        }`}
        onClick={onClose}
        aria-hidden="true"
      />

      <nav
        aria-label={t.topics}
        className={`fixed inset-y-0 left-0 z-[60] w-[85vw] max-w-[300px] shadow-[var(--shadow-lg)]
          lg:static lg:z-auto lg:w-[272px] lg:max-w-none lg:shadow-none lg:translate-x-0
          flex flex-col shrink-0 bg-[var(--bg-elevated)] border-r border-[var(--border)]
          transition-transform duration-200 ease-out ${isOpen ? 'translate-x-0' : '-translate-x-full'}`}
      >
        <div className="flex items-center gap-2 p-3">
          <button
            onClick={onNewQuestion}
            className="flex-1 flex items-center justify-center gap-2 h-10 rounded-md bg-accent-800 hover:bg-accent-700 dark:bg-accent-600 dark:hover:bg-accent-500 text-white text-[14px] font-medium transition-colors cursor-pointer"
          >
            <Plus className="w-4 h-4" />
            {t.newQuestion}
          </button>
          <button
            onClick={onClose}
            aria-label={t.closeTopics}
            className="lg:hidden flex items-center justify-center w-10 h-10 rounded-md text-[var(--text-muted)] hover:bg-[var(--bg-inset)] cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-2.5 pb-4">
          {threads.length > 0 && (
            <section className="mt-1 mb-5">
              <h2 className="flex items-center gap-2 px-2 py-1 text-[11.5px] font-semibold uppercase tracking-[0.06em] text-[var(--text)]">
                {t.recent}
                <span className="ml-auto font-mono text-[10.5px] font-normal text-[var(--text-faint)]">{threads.length}</span>
              </h2>
              <ul className="mt-0.5">
                {(showAllRecent ? threads : threads.slice(0, RECENT_COLLAPSED_COUNT)).map((thread) => {
                  const isActive = thread.thread_id === activeThreadId;
                  return (
                    <li key={thread.thread_id}>
                      <button
                        onClick={() => onOpenThread(thread.thread_id)}
                        disabled={isQuerying}
                        title={thread.title}
                        aria-current={isActive ? 'true' : undefined}
                        className={`w-full flex items-baseline gap-2 text-left px-2 py-[7px] rounded-md text-[13.5px] disabled:opacity-50 disabled:cursor-not-allowed transition-colors cursor-pointer ${
                          isActive
                            ? 'bg-[var(--bg-inset)] text-[var(--text)] font-medium'
                            : 'text-[var(--text-secondary)] hover:text-[var(--text)] hover:bg-[var(--bg-inset)]'
                        }`}
                      >
                        <span className="flex-1 truncate">{thread.title}</span>
                        {thread.questions > 1 && (
                          <span className="shrink-0 font-mono text-[10.5px] text-[var(--text-faint)]">{thread.questions}</span>
                        )}
                      </button>
                    </li>
                  );
                })}
              </ul>
              {threads.length > RECENT_COLLAPSED_COUNT && (
                <button
                  onClick={() => setShowAllRecent((prev) => !prev)}
                  aria-expanded={showAllRecent}
                  className="ml-2 mt-0.5 inline-flex items-center gap-1 px-2 py-1 rounded-md text-[12.5px] font-medium text-accent-700 dark:text-accent-300 hover:bg-[var(--bg-inset)] cursor-pointer"
                >
                  {showAllRecent ? t.showFewer : t.showAll(threads.length)}
                  <ChevronDown className={`w-3.5 h-3.5 transition-transform ${showAllRecent ? 'rotate-180' : ''}`} />
                </button>
              )}
            </section>
          )}

          {localizedDomains(lang).map((domain) => (
            <section key={domain.id} className="mt-4 first:mt-1">
              <h2 className="flex items-center gap-2 px-2 py-1 text-[11.5px] font-semibold uppercase tracking-[0.06em] text-[var(--text)]">
                <span className={`w-2 h-2 rounded-[2px] ${DOMAIN_TONE[domain.id].dot}`} />
                {domain.label}
                <span className="ml-auto font-mono text-[10.5px] font-normal text-[var(--text-faint)]">{domain.topics.length}</span>
              </h2>
              <ul className="mt-0.5">
                {(expanded[domain.id] ? domain.topics : domain.topics.slice(0, COLLAPSED_COUNT)).map((topic) => (
                  <li key={topic.title}>
                    <button
                      onClick={() => onAskTopic(topic.query)}
                      disabled={isQuerying}
                      title={topic.query}
                      className="w-full text-left pl-6 pr-2 py-[7px] rounded-md text-[13.5px] text-[var(--text-secondary)] hover:text-[var(--text)] hover:bg-[var(--bg-inset)] disabled:opacity-50 disabled:cursor-not-allowed transition-colors cursor-pointer truncate"
                    >
                      {topic.title}
                    </button>
                  </li>
                ))}
              </ul>
              {domain.topics.length > COLLAPSED_COUNT && (
                <button
                  onClick={() => setExpanded((prev) => ({ ...prev, [domain.id]: !prev[domain.id] }))}
                  aria-expanded={Boolean(expanded[domain.id])}
                  className="ml-6 mt-0.5 inline-flex items-center gap-1 px-2 py-1 rounded-md text-[12.5px] font-medium text-accent-700 dark:text-accent-300 hover:bg-[var(--bg-inset)] cursor-pointer"
                >
                  {expanded[domain.id] ? t.showFewer : t.showAll(domain.topics.length)}
                  <ChevronDown className={`w-3.5 h-3.5 transition-transform ${expanded[domain.id] ? 'rotate-180' : ''}`} />
                </button>
              )}
            </section>
          ))}
        </div>

        <div className="border-t border-[var(--border)] px-4 py-3 space-y-1.5 text-[12px] text-[var(--text-muted)]">
          <div className="flex items-center gap-2 text-emerald-700 dark:text-emerald-400 font-medium">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-600 dark:bg-emerald-400" />
            {t.officialSources(PROGRAMME.shortName)}
          </div>
          <div className="flex items-center justify-between gap-2">
            <VersionBadge />
            <VisitorCounter />
          </div>
        </div>
      </nav>
    </>
  );
};
