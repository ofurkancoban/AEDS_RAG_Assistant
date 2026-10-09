import React, { useEffect, useState } from 'react';
import { ChevronDown, Plus, X } from 'lucide-react';
import { PROGRAMME, DOMAIN_TONE } from '../../config/programme';
import { VersionBadge } from '../VersionBadge';
import { VisitorCounter } from '../VisitorCounter';

interface SideNavProps {
  isOpen: boolean;
  onClose: () => void;
  onNewQuestion: () => void;
  onAskTopic: (query: string) => void;
  isQuerying: boolean;
}

/* Topic navigation, filed by domain. A permanent column from lg up; below
   that a drawer opened from the header, so the conversation keeps the whole
   screen on a phone. */
// Long topic lists show this many until expanded, so every domain's heading
// stays within reach - on a phone the programme's list alone would otherwise
// push the other domains out of the drawer's first screen.
const COLLAPSED_COUNT = 6;

export const SideNav: React.FC<SideNavProps> = ({ isOpen, onClose, onNewQuestion, onAskTopic, isQuerying }) => {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
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
        aria-label="Topics"
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
            New question
          </button>
          <button
            onClick={onClose}
            aria-label="Close topics"
            className="lg:hidden flex items-center justify-center w-10 h-10 rounded-md text-[var(--text-muted)] hover:bg-[var(--bg-inset)] cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-2.5 pb-4">
          {PROGRAMME.domains.map((domain) => (
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
                  {expanded[domain.id] ? 'Show fewer' : `Show all ${domain.topics.length}`}
                  <ChevronDown className={`w-3.5 h-3.5 transition-transform ${expanded[domain.id] ? 'rotate-180' : ''}`} />
                </button>
              )}
            </section>
          ))}
        </div>

        <div className="border-t border-[var(--border)] px-4 py-3 space-y-1.5 text-[12px] text-[var(--text-muted)]">
          <div className="flex items-center gap-2 text-emerald-700 dark:text-emerald-400 font-medium">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-600 dark:bg-emerald-400" />
            Official {PROGRAMME.shortName} &amp; university sources
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
