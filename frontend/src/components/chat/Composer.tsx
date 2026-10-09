import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { ArrowUp, ChevronDown, CornerDownLeft, LayoutList, Loader2 } from 'lucide-react';
import { PROGRAMME, DOMAIN_TONE, DomainId, Topic } from '../../config/programme';
import { useMediaQuery } from './useMediaQuery';

interface ComposerProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onPickTopic: (query: string) => void;
  isQuerying: boolean;
  placeholder?: string;
}

const MAX_HEIGHT_PX = 168;

interface Entry {
  topic: Topic;
  domain: DomainId;
  index: number;
}

/* The topic index sits behind the "Topics" button and "/", grouped by
   domain like the side navigation, so the full list is one keystroke or one
   tap away on a phone where that navigation is a drawer. Typing after the
   slash filters it. */
export const Composer: React.FC<ComposerProps> = ({ value, onChange, onSubmit, onPickTopic, isQuerying, placeholder }) => {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const isWide = useMediaQuery('(min-width: 640px)');

  const [openedByButton, setOpenedByButton] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);

  const slashQuery = value.startsWith('/') ? value.slice(1).trim().toLowerCase() : null;
  const isMenuOpen = openedByButton || slashQuery !== null;

  const entries = useMemo(() => {
    const q = slashQuery ?? '';
    const all: Entry[] = [];
    for (const domain of PROGRAMME.domains) {
      for (const topic of domain.topics) {
        if (!q || `${topic.title} ${domain.label}`.toLowerCase().includes(q)) {
          all.push({ topic, domain: domain.id, index: all.length });
        }
      }
    }
    return all;
  }, [slashQuery]);

  useEffect(() => setActiveIndex(0), [slashQuery]);
  useEffect(() => {
    itemRefs.current[activeIndex]?.scrollIntoView({ block: 'nearest' });
  }, [activeIndex]);

  // Grows with what is typed, up to a cap, then scrolls.
  useLayoutEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT_PX)}px`;
  }, [value, isWide]);

  useEffect(() => {
    if (!isMenuOpen) return;
    const onDown = (e: MouseEvent) => {
      if (!containerRef.current?.contains(e.target as Node)) closeMenu();
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  });

  function closeMenu() {
    setOpenedByButton(false);
    if (value.startsWith('/')) onChange('');
  }

  function pick(topic: Topic) {
    setOpenedByButton(false);
    onChange('');
    onPickTopic(topic.query);
  }

  const canSend = !isQuerying && value.trim().length > 0 && slashQuery === null;

  return (
    <div>
      <div ref={containerRef} className="relative">
        {isMenuOpen && (
          <div
            className="absolute left-0 right-0 bottom-full mb-2 z-30 rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] shadow-[var(--shadow-lg)] overflow-hidden animate-in"
            role="listbox"
            aria-label="Topics"
          >
            <div className="flex items-center justify-between px-4 py-2.5 border-b border-[var(--border)]">
              <span className="text-[13.5px] font-semibold text-[var(--text)]">Topics</span>
              <span className="hidden sm:flex items-center gap-1.5 text-[11px] text-[var(--text-faint)]">
                <kbd className="kbd">↑</kbd><kbd className="kbd">↓</kbd> move <kbd className="kbd">↵</kbd> ask <kbd className="kbd">esc</kbd> close
              </span>
            </div>
            <div className="max-h-[min(360px,50dvh)] overflow-y-auto py-1">
              {entries.length === 0 ? (
                <p className="px-4 py-3 text-[13.5px] text-[var(--text-muted)]">
                  No topic matches "{slashQuery}". Press Escape and ask it as a question instead.
                </p>
              ) : (
                PROGRAMME.domains.map((domain) => {
                  const inDomain = entries.filter((e) => e.domain === domain.id);
                  if (inDomain.length === 0) return null;
                  return (
                    <div key={domain.id} className="py-1">
                      <div className="flex items-center gap-2 px-4 pt-1.5 pb-1 text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-muted)]">
                        <span className={`w-2 h-2 rounded-[2px] ${DOMAIN_TONE[domain.id].dot}`} />
                        {domain.label}
                      </div>
                      {inDomain.map(({ topic, index }) => {
                        const Icon = topic.icon;
                        const active = index === activeIndex;
                        return (
                          <button
                            key={topic.title}
                            ref={(el) => {
                              itemRefs.current[index] = el;
                            }}
                            role="option"
                            aria-selected={active}
                            onMouseEnter={() => setActiveIndex(index)}
                            onClick={() => pick(topic)}
                            className={`w-full flex items-center gap-3 px-4 py-2 text-left cursor-pointer ${active ? 'bg-accent-50 dark:bg-accent-500/15' : ''}`}
                          >
                            <Icon className={`w-4 h-4 shrink-0 ${active ? 'text-accent-700 dark:text-accent-300' : 'text-[var(--text-faint)]'}`} />
                            <span className="min-w-0 flex-1">
                              <span className="block text-[13.5px] font-medium text-[var(--text)]">{topic.title}</span>
                              <span className="block truncate text-[12px] text-[var(--text-muted)]">{topic.query}</span>
                            </span>
                            {active && <CornerDownLeft className="hidden sm:block w-3.5 h-3.5 shrink-0 text-[var(--text-faint)]" />}
                          </button>
                        );
                      })}
                    </div>
                  );
                })
              )}
            </div>
          </div>
        )}

        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (canSend) onSubmit();
          }}
          className="flex items-end gap-2 p-1.5 rounded-lg bg-[var(--bg-elevated)] border border-[var(--border-strong)] focus-within:border-accent-600 focus-within:ring-3 focus-within:ring-accent-500/15 dark:focus-within:border-accent-400 transition-shadow"
        >
          <button
            type="button"
            onClick={() => (isMenuOpen ? closeMenu() : setOpenedByButton(true))}
            aria-label="Browse topics"
            aria-expanded={isMenuOpen}
            title="Browse topics ( / )"
            className={`shrink-0 h-9 px-2.5 rounded-md flex items-center gap-1.5 text-[13px] font-medium transition-colors cursor-pointer ${
              isMenuOpen
                ? 'bg-accent-50 text-accent-800 dark:bg-accent-500/15 dark:text-accent-200'
                : 'bg-[var(--bg-inset)] text-[var(--text-secondary)] hover:text-[var(--text)]'
            }`}
          >
            <LayoutList className="w-4 h-4" />
            <span className="hidden sm:inline">Topics</span>
            <ChevronDown className={`w-3.5 h-3.5 transition-transform ${isMenuOpen ? 'rotate-180' : ''}`} />
          </button>

          <label htmlFor="chat-input" className="sr-only">Ask a question</label>
          <textarea
            id="chat-input"
            ref={textareaRef}
            rows={1}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={(e) => {
              if (isMenuOpen) {
                if (e.key === 'ArrowDown') {
                  e.preventDefault();
                  setActiveIndex((i) => Math.min(i + 1, entries.length - 1));
                  return;
                }
                if (e.key === 'ArrowUp') {
                  e.preventDefault();
                  setActiveIndex((i) => Math.max(i - 1, 0));
                  return;
                }
                if (e.key === 'Escape') {
                  e.preventDefault();
                  closeMenu();
                  return;
                }
                if (e.key === 'Enter' && !e.shiftKey && entries[activeIndex] && (slashQuery !== null || !value.trim())) {
                  e.preventDefault();
                  pick(entries[activeIndex].topic);
                  return;
                }
              }
              if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                if (canSend) onSubmit();
              }
            }}
            placeholder={placeholder ?? (isWide ? 'Ask a question, e.g. When is the deadline for the winter semester?' : 'Ask a question…')}
            disabled={isQuerying}
            // 16px on phones: iOS Safari zooms the page in on focus for any
            // input under 16px.
            className="flex-1 min-w-0 self-center resize-none bg-transparent px-1 py-1.5 text-base sm:text-[15px] leading-6 text-[var(--text)] placeholder:text-[var(--text-faint)] focus:outline-none disabled:opacity-60"
          />
          <button
            type="submit"
            disabled={!canSend}
            aria-label="Send question"
            title="Send (Enter)"
            className="shrink-0 w-9 h-9 rounded-md flex items-center justify-center bg-accent-800 hover:bg-accent-700 dark:bg-accent-600 dark:hover:bg-accent-500 text-white disabled:bg-[var(--bg-inset)] disabled:text-[var(--text-faint)] transition-colors cursor-pointer disabled:cursor-not-allowed"
          >
            {isQuerying ? <Loader2 className="w-4 h-4 animate-spin" /> : <ArrowUp className="w-[18px] h-[18px]" />}
          </button>
        </form>
      </div>

      {/* Said plainly and before the fact: people are entitled to know their
          questions are kept and read by a person. */}
      <div className="mt-2 flex items-start justify-between gap-4 text-[11.5px] leading-snug text-[var(--text-muted)]">
        <span>
          Questions and answers are stored and reviewed by the programme team.{' '}
          <strong className="font-medium text-[var(--text-secondary)]">Do not enter personal information.</strong>
        </span>
        <span className="hidden md:inline whitespace-nowrap text-[var(--text-faint)]">Enter to send · / for topics</span>
      </div>
    </div>
  );
};
