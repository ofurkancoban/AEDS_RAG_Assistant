import React, { useState, useRef, useEffect, useMemo } from 'react';
import { ArrowUpRight, FileText, ShieldCheck, Clock, Plus } from 'lucide-react';
import { ChatQueryResult, RetrievalDiagnostic } from '../types';
import { rateAnswer, streamChatMessage, submitFeedback } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { BrandMark } from './BrandMark';
import { Exchange, ChatMessage } from './chat/Exchange';
import { Composer } from './chat/Composer';
import { SideNav } from './chat/SideNav';
import { EvidencePanel } from './chat/Sources';
import { ChunkDetailModal, SuggestKnowledgeModal } from './chat/ChatModals';
import { citationCounts, stripCitations } from './chat/citations';
import { useMediaQuery } from './chat/useMediaQuery';
import { WELCOME_MESSAGES, pickRandom, prefersReducedMotion } from './chat/content';
import { PROGRAMME, DOMAIN_TONE } from '../config/programme';

interface RagChatViewProps {
  onQueryResult?: (result: ChatQueryResult) => void;
  /** Below lg the topic navigation is a drawer; App owns whether it is
      open because the button that opens it lives in the header. */
  isNavOpen: boolean;
  onNavOpenChange: (open: boolean) => void;
}

interface ExchangeData {
  question: ChatMessage;
  answer?: ChatMessage;
}

function nowLabel(): string {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function toExchanges(messages: ChatMessage[]): ExchangeData[] {
  const exchanges: ExchangeData[] = [];
  for (const msg of messages) {
    if (msg.sender === 'user') exchanges.push({ question: msg });
    else if (exchanges.length > 0 && !exchanges[exchanges.length - 1].answer) {
      exchanges[exchanges.length - 1].answer = msg;
    }
  }
  return exchanges;
}

/** The welcome messages are written as greeting / joke / instruction; the
    start screen already gives the instructions, so only the joke is kept. */
function jokeOf(message: string): string {
  const paragraphs = message.split(/\n\n+/).map((p) => p.trim()).filter(Boolean);
  const body = paragraphs.length > 2 ? paragraphs.slice(1, -1) : paragraphs.slice(1);
  return (body.length ? body : paragraphs).join(' ').replace(/\*\*/g, '');
}

export const RagChatView: React.FC<RagChatViewProps> = ({ onQueryResult, isNavOpen, onNavOpenChange }) => {
  const { isAdmin } = useAuth();
  const isXL = useMediaQuery('(min-width: 1280px)');

  const [queryInput, setQueryInput] = useState('');
  const [isQuerying, setIsQuerying] = useState(false);
  const [stages, setStages] = useState<string[]>([]);
  const [pendingStartedAt, setPendingStartedAt] = useState(0);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [selectedChunk, setSelectedChunk] = useState<RetrievalDiagnostic | null>(null);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [ratings, setRatings] = useState<Record<string, 1 | -1>>({});
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  // null follows the newest question; set when the reader picks an older one.
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [activeCitation, setActiveCitation] = useState<number | null>(null);

  const [isSuggestModalOpen, setIsSuggestModalOpen] = useState(false);
  const [suggestSourceId, setSuggestSourceId] = useState('general');
  const [suggestContent, setSuggestContent] = useState('');
  const [suggestType, setSuggestType] = useState<'new_info' | 'correction'>('new_info');
  const [isSubmittingKnowledge, setIsSubmittingKnowledge] = useState(false);
  const [submitSuccessMsg, setSubmitSuccessMsg] = useState<string | null>(null);

  const [welcomeJoke] = useState(() => jokeOf(pickRandom(WELCOME_MESSAGES)));
  const lastCardRef = useRef<HTMLDivElement>(null);

  const exchanges = useMemo(() => toExchanges(messages), [messages]);
  const hasStarted = exchanges.length > 0;
  const selected =
    exchanges.find((e) => e.question.id === selectedId) ?? exchanges[exchanges.length - 1];
  const selectedRetrieval = selected?.answer?.resultData?.retrieval ?? [];
  const selectedCounts = useMemo(() => citationCounts(selected?.answer?.text ?? ''), [selected?.answer?.text]);

  // A new question scrolls its card into view at the top, so its answer
  // streams in below where the reader already is.
  useEffect(() => {
    if (exchanges.length === 0) return;
    lastCardRef.current?.scrollIntoView({ behavior: prefersReducedMotion() ? 'auto' : 'smooth', block: 'start' });
  }, [exchanges.length]);

  const closeNav = () => onNavOpenChange(false);

  const handleNewQuestion = () => {
    setThreadId(null);
    setMessages([]);
    setSelectedId(null);
    setActiveCitation(null);
    closeNav();
  };

  const handleCopy = (text: string, id: string) => {
    navigator.clipboard.writeText(stripCitations(text));
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const openSuggest = () => {
    setIsSuggestModalOpen(true);
    setSuggestContent('');
  };

  const handleSuggestSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!suggestContent.trim()) return;

    setIsSubmittingKnowledge(true);
    try {
      await submitFeedback({
        submission_type: suggestType,
        source_id: suggestSourceId || 'general',
        content: suggestContent,
      });
      setSubmitSuccessMsg('Submitted to the admin review queue - it will be indexed once approved.');
      setTimeout(() => {
        setIsSuggestModalOpen(false);
        setSubmitSuccessMsg(null);
        setSuggestContent('');
      }, 2200);
    } catch (err: any) {
      console.error('Failed to submit knowledge:', err);
      alert(err.message || 'Failed to submit');
    } finally {
      setIsSubmittingKnowledge(false);
    }
  };

  const handleRate = async (msgId: string, logId: number, rating: 1 | -1) => {
    setRatings((prev) => ({ ...prev, [msgId]: rating }));
    try {
      await rateAnswer(logId, rating);
    } catch (err) {
      console.error('Failed to submit rating:', err);
      setRatings((prev) => {
        const next = { ...prev };
        delete next[msgId];
        return next;
      });
    }
  };

  const handleRunQuery = async (queryToRun?: string) => {
    const textToSubmit = (queryToRun || queryInput).trim();
    if (!textToSubmit || isQuerying) return;

    closeNav();
    const userMsgId = `usr-${Date.now()}`;
    const assistantMsgId = `ast-${Date.now()}`;

    setMessages((prev) => [...prev, { id: userMsgId, sender: 'user', text: textToSubmit, timestamp: nowLabel() }]);
    if (!queryToRun) setQueryInput('');
    setSelectedId(null);
    setActiveCitation(null);
    setStages([]);
    setPendingStartedAt(Date.now());
    setIsQuerying(true);

    try {
      const askedAt = Date.now();

      await streamChatMessage(textToSubmit, threadId, null, {
        onStage: (stage) => setStages((prev) => (prev.includes(stage) ? prev : [...prev, stage])),
        onToken: (text) => {
          setIsQuerying(false);
          // Whether the answer exists is read from `prev`, not from a flag in
          // this closure: React calls updaters twice under StrictMode, and a
          // flag flipped inside one made every later token map over an array
          // without the answer in it.
          setMessages((prev) => {
            if (prev.some((m) => m.id === assistantMsgId)) {
              return prev.map((m) => (m.id === assistantMsgId ? { ...m, text: m.text + text } : m));
            }
            return [...prev, { id: assistantMsgId, sender: 'assistant', text, timestamp: nowLabel() }];
          });
        },
        onDone: (data) => {
          setThreadId(data.thread_id);

          const result: ChatQueryResult = {
            id: `res-${Date.now()}`,
            query: textToSubmit,
            answer: data.final_answer,
            sources: data.sources ?? [],
            retrieval: data.retrieval ?? [],
            nodeLatencies: data.node_latencies ?? {},
            autoFlaggedContribution: data.auto_flagged_contribution ?? null,
            timestamp: Date.now(),
            queryLogId: data.query_log_id ?? null,
            cached: Boolean(data.cached),
            elapsedMs: Date.now() - askedAt,
            hasExpiredDeadline: Boolean(data.has_expired_deadline),
          };

          // final_answer is authoritative - the generate node strips
          // fabricated citations and invalid passage numbers after the raw
          // tokens were already streamed.
          setMessages((prev) => {
            if (!prev.some((m) => m.id === assistantMsgId)) {
              return [
                ...prev,
                { id: assistantMsgId, sender: 'assistant', text: data.final_answer, timestamp: nowLabel(), resultData: result },
              ];
            }
            return prev.map((m) =>
              m.id === assistantMsgId ? { ...m, text: data.final_answer, resultData: result } : m
            );
          });
          onQueryResult?.(result);
        },
      });
    } catch (error: any) {
      console.error('Error executing RAG query:', error);
      setMessages((prev) => [
        ...prev,
        {
          id: `err-${Date.now()}`,
          sender: 'assistant',
          text: `**The answer could not be loaded.** ${error?.message || 'Server connection failed. Please try again.'}`,
          timestamp: nowLabel(),
        },
      ]);
    } finally {
      setIsQuerying(false);
    }
  };

  return (
    <div className="h-full flex">
      <SideNav
        isOpen={isNavOpen}
        onClose={closeNav}
        onNewQuestion={handleNewQuestion}
        onAskTopic={(query) => handleRunQuery(query)}
        isQuerying={isQuerying}
      />

      <section className="flex-1 min-w-0 flex flex-col" aria-label="Assistant">
        <div className="flex-1 min-h-0 overflow-y-auto">
          {!hasStarted ? (
            <div className="max-w-[880px] mx-auto px-4 sm:px-8 py-7 sm:py-12 animate-fade-up">
              <p className="eyebrow">
                {PROGRAMME.name} · {PROGRAMME.degree}
              </p>
              <h1 className="mt-2 text-[26px] sm:text-[32px] font-semibold leading-tight tracking-[-0.015em] text-[var(--text)]">
                How can we help?
              </h1>
              <p className="mt-2 max-w-[62ch] text-[15px] sm:text-[16px] leading-relaxed text-[var(--text-secondary)]">
                Ask about your programme, the university or life in {PROGRAMME.city}. Every answer is drawn
                from official documents and shows its sources.
              </p>

              <div className="mt-6 sm:mt-8 grid gap-3.5 md:grid-cols-3">
                {PROGRAMME.domains.map((domain) => {
                  const Icon = domain.icon;
                  return (
                    <section key={domain.id} className="rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] p-4 flex flex-col">
                      <div className="flex items-center gap-2.5">
                        <span className={`w-8 h-8 rounded-md flex items-center justify-center ${DOMAIN_TONE[domain.id].icon}`}>
                          <Icon className="w-4 h-4" />
                        </span>
                        <h2 className="text-[15px] font-semibold text-[var(--text)]">{domain.label}</h2>
                      </div>
                      <p className="mt-1.5 mb-2 text-[12.5px] text-[var(--text-muted)]">{domain.description}</p>
                      <ul className="mt-auto">
                        {domain.starters.map((starter) => (
                          <li key={starter} className="border-t border-[var(--border)]">
                            <button
                              onClick={() => handleRunQuery(starter)}
                              disabled={isQuerying}
                              className="group w-full flex items-start gap-2 py-2.5 text-left text-[13.5px] leading-snug text-[var(--text-secondary)] hover:text-accent-700 dark:hover:text-accent-300 disabled:opacity-60 cursor-pointer"
                            >
                              <span className="flex-1">{starter}</span>
                              <ArrowUpRight className="w-3.5 h-3.5 mt-0.5 shrink-0 text-[var(--text-faint)] group-hover:text-accent-700 dark:group-hover:text-accent-300" />
                            </button>
                          </li>
                        ))}
                      </ul>
                    </section>
                  );
                })}
              </div>

              <ul className="mt-5 flex flex-wrap gap-x-6 gap-y-2 text-[12.5px] text-[var(--text-muted)]">
                <li className="inline-flex items-center gap-1.5"><FileText className="w-3.5 h-3.5" />Official programme &amp; university sources</li>
                <li className="inline-flex items-center gap-1.5"><ShieldCheck className="w-3.5 h-3.5" />Answers reviewed by programme staff</li>
                <li className="inline-flex items-center gap-1.5"><Clock className="w-3.5 h-3.5" />Outdated sources are flagged</li>
              </ul>

              {/* The assistant's own voice, kept small: the platform is an
                  official service, but a line of personality on the way in
                  costs nothing. */}
              <aside className="mt-8 flex items-start gap-3 rounded-lg border border-dashed border-[var(--border-strong)] px-4 py-3">
                <BrandMark size={24} className="mt-0.5" />
                <p className="text-[13px] leading-relaxed text-[var(--text-muted)]">
                  <span className="font-medium text-[var(--text-secondary)]">From the assistant: </span>
                  {welcomeJoke}
                </p>
              </aside>
            </div>
          ) : (
            <div className="max-w-[780px] mx-auto px-3 sm:px-6 pb-8">
              <div className="sticky top-0 z-10 -mx-3 sm:-mx-6 px-3 sm:px-6 py-2.5 mb-2 flex items-center justify-between bg-[var(--bg)]/90 backdrop-blur-sm">
                <span className="text-[12.5px] text-[var(--text-muted)]">
                  This conversation · {exchanges.length} {exchanges.length === 1 ? 'question' : 'questions'}
                </span>
                <button
                  onClick={handleNewQuestion}
                  disabled={isQuerying}
                  className="inline-flex items-center gap-1.5 h-8 px-2.5 -mr-2 rounded-md text-[13px] font-medium text-[var(--text-secondary)] hover:text-[var(--text)] hover:bg-[var(--bg-inset)] disabled:opacity-50 cursor-pointer"
                >
                  <Plus className="w-4 h-4" />
                  New question
                </button>
              </div>

              <div className="space-y-4">
                {exchanges.map((exchange, idx) => {
                  const isLast = idx === exchanges.length - 1;
                  const qid = exchange.question.id;
                  return (
                    <div key={qid} ref={isLast ? lastCardRef : undefined} className="scroll-mt-14">
                      <Exchange
                        question={exchange.question}
                        answer={exchange.answer}
                        isPending={isLast && isQuerying}
                        stages={stages}
                        startedAt={pendingStartedAt}
                        isSelected={isXL && selected?.question.id === qid && exchanges.length > 1}
                        showInlineSources={!isXL}
                        activeCitation={selected?.question.id === qid ? activeCitation : null}
                        isAdmin={isAdmin}
                        isCopied={copiedId === exchange.answer?.id}
                        rating={exchange.answer ? ratings[exchange.answer.id] : undefined}
                        onSelect={() => {
                          if (selected?.question.id !== qid) setActiveCitation(null);
                          setSelectedId(qid);
                        }}
                        onCitation={(n, item) => {
                          if (isXL) {
                            setSelectedId(qid);
                            setActiveCitation(n);
                          } else {
                            setSelectedChunk(item);
                          }
                        }}
                        onOpenPassage={setSelectedChunk}
                        onCopy={() => exchange.answer && handleCopy(exchange.answer.text, exchange.answer.id)}
                        onRate={(logId, rating) => exchange.answer && handleRate(exchange.answer.id, logId, rating)}
                        onSuggestCorrection={openSuggest}
                      />
                    </div>
                  );
                })}
              </div>
              {/* Room below the newest card so it can scroll to the top of
                  the view while its answer is still short. */}
              <div className="h-[40dvh]" aria-hidden="true" />
            </div>
          )}
        </div>

        <div className="shrink-0 border-t border-[var(--border)] bg-[var(--bg-elevated)] px-3 sm:px-6 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
          <div className="max-w-[780px] mx-auto">
            <Composer
              value={queryInput}
              onChange={setQueryInput}
              onSubmit={() => handleRunQuery()}
              onPickTopic={(query) => handleRunQuery(query)}
              isQuerying={isQuerying}
              placeholder={hasStarted ? 'Ask a follow-up question' : undefined}
            />
          </div>
        </div>
      </section>

      <EvidencePanel
        question={selected?.answer?.resultData ? selected.question.text : undefined}
        retrieval={selectedRetrieval}
        counts={selectedCounts}
        activeCitation={activeCitation}
        onOpenPassage={setSelectedChunk}
        onSuggestCorrection={openSuggest}
      />

      <ChunkDetailModal chunk={selectedChunk} onClose={() => setSelectedChunk(null)} />

      <SuggestKnowledgeModal
        isOpen={isSuggestModalOpen}
        onClose={() => setIsSuggestModalOpen(false)}
        onSubmit={handleSuggestSubmit}
        type={suggestType}
        onTypeChange={setSuggestType}
        sourceId={suggestSourceId}
        onSourceIdChange={setSuggestSourceId}
        content={suggestContent}
        onContentChange={setSuggestContent}
        isSubmitting={isSubmittingKnowledge}
        successMessage={submitSuccessMsg}
      />
    </div>
  );
};
