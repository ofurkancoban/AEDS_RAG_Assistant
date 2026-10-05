import React, { useState, useRef, useEffect, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
// Without gfm, ReactMarkdown leaves pipe tables as literal "|---|" text - and
// the system prompt explicitly invites the model to answer with a table when
// a fact varies by category.
import remarkGfm from 'remark-gfm';
import { ANSWER_MARKDOWN_COMPONENTS } from './markdown';
import { ThinkingIndicator } from './ThinkingIndicator';
import { ChatQueryResult, RetrievalDiagnostic } from '../types';
import { rateAnswer, streamChatMessage, submitFeedback } from '../api/client';
import { useAuth } from '../context/AuthContext';
import {
  Send, FileText, CheckCircle2,
  Zap, RefreshCw, ShieldCheck, PlusCircle, X, Menu,
  Plus, Copy, Timer,
  Check, ChevronRight, ChevronDown, Layers, ThumbsUp, ThumbsDown,
  // Quick Academic Queries - one per topic, see ACADEMIC_TOPICS below.
  CalendarClock, ClipboardCheck, Languages, PieChart, ListChecks,
  CalendarRange, Globe, UserSearch, ScrollText, GraduationCap,
  FileWarning, Stethoscope, Mail, Briefcase, BadgeCheck
} from 'lucide-react';

interface RagChatViewProps {
  onOpenAdminMode?: () => void;
  onQueryResult?: (result: ChatQueryResult) => void;
}

interface ChatMessage {
  id: string;
  sender: 'user' | 'assistant';
  text: string;
  timestamp: string;
  resultData?: ChatQueryResult;
}

// The four topics students actually ask about most (measured from query_log:
// thesis rules, curriculum, deadlines, exams), phrased generally rather than
// for one group. The deadline question used to read "for non-EU applicants",
// which quietly assumed something about whoever was reading it; asked plainly
// it returns the whole table, because the prompt tells the model to answer for
// every category when the question names none.
//
// Every wording here has been run through the real pipeline and answers from
// the documents - a suggestion that lands in a content gap is worse than no
// suggestion. Lengths are kept close so each sits on one line in the grid
// below. The sidebar still offers every topic as a one-click shortcut; these
// exist to show a newcomer how to phrase a question of their own.
/* Sub-second answers come from the reviewed-answer store and are the point of
   it, so they are worth showing as such rather than as "0.4s". Everything else
   is rounded to a tenth up to a minute, then to whole seconds - at that length
   the tenth is noise. */
function formatElapsed(ms: number): string {
  if (ms < 1000) return 'instant';
  const seconds = ms / 1000;
  return seconds < 60 ? `${seconds.toFixed(1)}s` : `${Math.round(seconds)}s`;
}

const SUGGESTED_QUERIES = [
  'What are the application deadlines?',
  'What courses are in the curriculum?',
  'What are the rules for the Master Thesis?',
  'How many times can I retake a failed module exam?',
];

// Each entry is a question the golden eval (tests/golden_qa.json) confirms the
// corpus can actually answer, so the shortcuts never send a student into a
// content gap. Icons are picked to match the subject - the previous set paired
// deadlines with a currency symbol and ECTS credits with an AI-brain glyph.
const ACADEMIC_TOPICS = [
  {
    title: 'Application Deadlines',
    badge: 'Admissions',
    query: 'What are the application deadlines for Non-EU, EU, and German applicants?',
    icon: CalendarClock,
  },
  {
    title: 'Admission Requirements',
    badge: 'Admissions',
    query:
      "How many ECTS credits must an applicant's prior Bachelor's degree be worth, and how many in Economics, Statistics, and Econometrics?",
    icon: ClipboardCheck,
  },
  {
    title: 'Language Requirements',
    badge: 'Admissions',
    query: 'What are the language requirements for admission?',
    icon: Languages,
  },
  {
    title: 'ECTS Distribution',
    badge: 'Curriculum',
    query: 'How are the 120 ECTS distributed across semesters and subject areas?',
    icon: PieChart,
  },
  {
    title: 'Compulsory Courses',
    badge: 'Curriculum',
    query: 'Which courses are compulsory?',
    icon: ListChecks,
  },
  {
    title: 'First Semester Plan',
    badge: 'Curriculum',
    query: 'Which compulsory courses are usually taken in the first semester?',
    icon: CalendarRange,
  },
  {
    title: 'German-Taught Courses',
    badge: 'Curriculum',
    query: 'Which courses are taught only in German?',
    icon: Globe,
  },
  {
    title: 'Teaching Staff',
    badge: 'Faculty',
    // Returns the whole roster grouped by professor. Verified against the
    // Course table: 36 of 37 course-to-professor pairs correct, none wrong.
    query: 'Which professors teach on this programme, and which courses do they teach?',
    icon: UserSearch,
  },
  {
    title: 'Master Thesis Rules',
    badge: 'Thesis',
    query: 'What are the rules for writing, extending, and submitting the Master Thesis?',
    icon: ScrollText,
  },
  {
    title: 'Thesis Credits & Grading',
    badge: 'Thesis',
    query:
      'How many ECTS is the thesis module worth, and how long does grading take after submission?',
    icon: GraduationCap,
  },
  {
    title: 'Retaking a Failed Exam',
    badge: 'Examinations',
    query: 'How many times can I retake a failed module exam?',
    icon: FileWarning,
  },
  {
    title: 'Illness on Exam Day',
    badge: 'Examinations',
    query: "What should I do if I'm ill on the day of an exam?",
    icon: Stethoscope,
  },
  {
    title: 'Examinations Office',
    badge: 'Contact',
    query: 'Who is the contact person at the examinations office?',
    icon: Mail,
  },
  {
    title: 'Career Prospects',
    badge: 'Careers',
    query: 'What kind of employers hire graduates of this programme?',
    icon: Briefcase,
  },
  {
    title: 'Programme Accreditation',
    badge: 'Accreditation',
    query: 'When does the accreditation for this programme expire?',
    icon: BadgeCheck,
  },
];

// One of these greets the visitor per session. They are jokes at the
// assistant's own expense rather than at the reader's, and each still says what
// it can actually do - the welcome message is the first thing a new student
// sees, so being funny must not cost them the instructions.
const WELCOME_MESSAGES = [
  `**Welcome to the AEDS assistant.**

Unlike your econometrics model, I do not overfit. Ask me about the curriculum, deadlines, exams, or thesis rules, and I will quote the official documents rather than improvise.`,

  `**Hello.**

I have read every module handbook, exam regulation, and programme flyer so that you do not have to. None of it counts towards your 120 ECTS, which I consider a personal injustice.

What would you like to know?`,

  `**Welcome.**

I will never confuse correlation with causation, mainly because I just quote the documents and leave the inference to you.

Curriculum, admissions, exams, thesis rules: ask away.`,

  `**AEDS assistant online.**

Other chatbots invent facts with total confidence. I have a strict document-grounding policy, which is a formal way of saying I would rather admit I do not know than make something up.

Try one of the questions on the left, or ask your own.`,

  `**Good to see you.**

I can tell you the curriculum, the exam regulations, the thesis rules, and every application deadline. I cannot tell you where you left your student ID.

Ask me the ones I can actually answer.`,

  `**Welcome to the AEDS assistant.**

Everything I say holds ceteris paribus, and by that I mean until the programme office updates the PDF.

Ask about courses, admissions, exams, or the thesis.`,

  `**Hi there.**

I run on a local language model and zero coffee, which already makes me better rested than most Master's students.

Ask me anything about the programme.`,

  `**AEDS assistant, ready.**

If you are here at 2am asking about application deadlines, I have both good news and bad news, and both of them are in the official documents.

Let us find out which one applies to you.`,

  `**Welcome.**

I stay strictly neutral on R versus Python. I am, however, deeply partisan about citing my sources.

Curriculum, deadlines, exams, thesis: pick one.`,

  `**Hello and welcome.**

Every answer I give is significant at the p < 0.05 level. That is a joke. Every answer I give comes with a citation, which is considerably more useful.

What can I look up for you?`,

  `**AEDS assistant here.**

I was optimised for exactly one objective function: answering your programme questions from the official documents. Subject to one constraint, which is no guessing.

Ask away.`,

  `**Welcome.**

I use hybrid retrieval, which is a fancy way of saying I check twice before answering. Your thesis supervisor should adopt the same policy.

Ask about the curriculum, deadlines, exams, or thesis rules.`,

  `**AEDS assistant, at your service.**

I run locally, so nothing you ask me leaves this server to train someone else's model. Your secrets about not having started the thesis yet are safe with me.

What do you need?`,

  `**Hello.**

I have a strict no-hallucination policy, enforced not by willpower but by a relevance threshold that refuses to answer when the documents do not cover it. Best safety feature I have.

Curriculum, admissions, exams, thesis: your call.`,

  `**Good to see you.**

Somewhere out there is a chatbot confidently inventing a deadline that does not exist. I am not that chatbot. I would rather say "the documents do not say" than guess.

Ask me something I can actually check.`,

  `**Welcome to the AEDS assistant.**

I treat every document like a null hypothesis: I do not reject "I don't know" without sufficient evidence.

Ask about courses, admissions, exams, or the thesis.`,

  `**Hi.**

I do not get tired, distracted, or annoyed by the same deadline question asked for the third time today. Genuinely, ask it again if you need to.

What would you like to know?`,

  `**AEDS assistant online.**

My training objective was answering your questions, not sounding impressive doing it. So expect citations over confidence.

Try a question on the left, or ask your own.`,

  `**Hey.**

I read the entire module handbook so you don't have to, which took me about half a second. It took whoever wrote it several months and at least one existential crisis.

Ask me about courses, deadlines, exams, or the thesis.`,

  `**Welcome.**

I don't procrastinate, I don't need five coffees to function, and I have never once said "I'll start the assignment tomorrow." I know, I'm insufferable.

What can I look up for you?`,

  `**AEDS assistant, reporting for duty.**

Somewhere a professor is holding office hours that nobody attends. I am always available, judge nobody, and have unlimited patience for "wait, when's that due again?"

Ask away.`,

  `**Hi there.**

I do not eat, sleep, or panic at 3am before a deadline. I do panic slightly if you ask me something the documents don't cover, which is the closest thing I have to stress.

Curriculum, deadlines, exams, thesis: your choice.`,

  `**Good to see you.**

Every group project has one person who does all the work and four who show up for the presentation. I am that one person. Unfortunately I cannot join your actual group project.

Ask me something I can actually help with.`,

  `**Welcome to the AEDS assistant.**

The wifi in the lecture hall may or may not work today. I, on the other hand, am always online, which is either impressive or deeply concerning.

What would you like to know?`,

  `**Hello.**

I have never once pulled an all-nighter, mostly because I don't have nights, or days, or a concept of time. Must be nice not needing coffee to function. Oh wait, that's also me.

Ask about courses, admissions, exams, or the thesis.`,

  `**AEDS assistant here.**

If procrastination were a competitive sport, several of you would already have a Master's degree in it. Luckily, I don't judge, I just answer questions about the programme.

Try a question on the left, or ask your own.`,
];

const NEW_CHAT_MESSAGES = [
  `**Fresh chat, clean slate.** Previous turns forgotten, sources still cited.`,
  `**New chat started.** My memory of the last one is gone. The documents remain.`,
  `**Starting over.** Ask any question about the programme.`,
  `**New thread.** Same documents, no baggage.`,
  `**Cleared.** What would you like to know?`,
];

function pickRandom<T>(options: T[]): T {
  return options[Math.floor(Math.random() * options.length)];
}

const WELCOME_ID = 'welcome-1';
// A beat before the first characters, so it reads as the assistant answering
// rather than as a page that rendered late.
const TYPING_START_DELAY_MS = 260;
const TYPING_TICK_MS = 16;

function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined'
    && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches === true;
}

export const RagChatView: React.FC<RagChatViewProps> = ({ onOpenAdminMode, onQueryResult }) => {
  const { isAdmin, email } = useAuth();
  const [queryInput, setQueryInput] = useState('');
  const [isQuerying, setIsQuerying] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [selectedChunk, setSelectedChunk] = useState<RetrievalDiagnostic | null>(null);
  const [expandedCitationsMsgId, setExpandedCitationsMsgId] = useState<string | null>(null);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [ratings, setRatings] = useState<Record<string, 1 | -1>>({});

  // Mobile only: the sidebar is a slide-over drawer there (closed by
  // default) instead of a column sharing the screen with the conversation,
  // which otherwise left too little height for the conversation to be
  // usable. Irrelevant above the lg breakpoint, where the sidebar is a
  // permanent column regardless of this flag.
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);

  const [isSuggestModalOpen, setIsSuggestModalOpen] = useState(false);
  const [suggestSourceId, setSuggestSourceId] = useState('general');
  const [suggestContent, setSuggestContent] = useState('');
  const [suggestType, setSuggestType] = useState<'new_info' | 'correction'>('new_info');
  const [isSubmittingKnowledge, setIsSubmittingKnowledge] = useState(false);
  const [submitSuccessMsg, setSubmitSuccessMsg] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Lazy initialisers so the greeting is drawn once per mount rather than on
  // every re-render - otherwise it would shuffle mid-conversation.
  const [welcomeText] = useState(() => pickRandom(WELCOME_MESSAGES));
  const [messages, setMessages] = useState<ChatMessage[]>(() => [
    {
      id: WELCOME_ID,
      sender: 'assistant',
      // Starts empty and fills in below. Anyone who has asked not to see
      // motion gets the whole thing at once instead.
      text: prefersReducedMotion() ? welcomeText : '',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    },
  ]);

  const typingTimerRef = useRef<number | null>(null);
  // Set once the visitor does something: whatever is typing then completes at
  // once rather than continuing underneath their question.
  const skipTypingRef = useRef(false);

  const stopTyping = useCallback(() => {
    if (typingTimerRef.current !== null) {
      window.clearTimeout(typingTimerRef.current);
      typingTimerRef.current = null;
    }
  }, []);

  /** Reveals a canned message the way a generated answer arrives.
   *
   * These texts are constants, so there is nothing to stream from the server -
   * the effect is produced client-side. It advances in uneven chunks rather
   * than fixed characters because that is how real token bursts land, and a
   * perfectly even crawl reads as an animation instead of as an answer.
   */
  const typeOutMessage = useCallback(
    (id: string, fullText: string) => {
      stopTyping();
      skipTypingRef.current = false;

      const write = (text: string) =>
        setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, text } : m)));

      // Anyone who asked not to see motion gets the whole thing at once.
      if (prefersReducedMotion()) {
        write(fullText);
        return;
      }

      let revealed = 0;
      const step = () => {
        revealed = skipTypingRef.current
          ? fullText.length
          : Math.min(fullText.length, revealed + 2 + Math.floor(Math.random() * 4));

        write(fullText.slice(0, revealed));

        typingTimerRef.current =
          revealed < fullText.length ? window.setTimeout(step, TYPING_TICK_MS) : null;
      };

      typingTimerRef.current = window.setTimeout(step, TYPING_START_DELAY_MS);
    },
    [stopTyping]
  );

  useEffect(() => {
    typeOutMessage(WELCOME_ID, welcomeText);
    return stopTyping;
  }, [welcomeText, typeOutMessage, stopTyping]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isQuerying]);

  const handleCopy = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleNewChat = () => {
    setThreadId(null);

    const id = `newchat-${Date.now()}`;
    const text = pickRandom(NEW_CHAT_MESSAGES);
    setMessages([
      {
        id,
        sender: 'assistant',
        text: prefersReducedMotion() ? text : '',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      },
    ]);
    // Cancels any greeting still typing and starts this one in its place.
    typeOutMessage(id, text);
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
    if (!textToSubmit) return;

    // The greeting finishes at once rather than continuing to type itself
    // above a question the visitor has already asked.
    skipTypingRef.current = true;

    const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const userMsgId = `usr-${Date.now()}`;
    const assistantMsgId = `ast-${Date.now()}`;

    setMessages((prev) => [...prev, { id: userMsgId, sender: 'user', text: textToSubmit, timestamp: timeStr }]);
    if (!queryToRun) setQueryInput('');
    setIsQuerying(true);

    try {
      // Streamed rather than awaited whole: retrieval alone can take many
      // seconds, so tokens are appended to a placeholder message as they
      // arrive instead of leaving the user on a spinner until the end.
      const askedAt = Date.now();

      await streamChatMessage(textToSubmit, threadId, null, {
        onToken: (text) => {
          setIsQuerying(false);
          // Whether the bubble exists is read from `prev`, not from a flag in
          // this closure. It used to be a `let started` that the updater set
          // on its first run - which is a side effect inside a state updater,
          // and React calls updaters twice under StrictMode. The first call
          // flipped the flag and returned the array with the new message; the
          // second saw the flag already set, took the map branch over the
          // unchanged `prev`, found nothing to update and returned it as-is.
          // React keeps the second result, so the bubble was never added and
          // every later token mapped over an array without it. The answer
          // then appeared complete in one piece when onDone created it: 131
          // token events arrived and not one of them reached the screen.
          setMessages((prev) => {
            if (prev.some((m) => m.id === assistantMsgId)) {
              return prev.map((m) => (m.id === assistantMsgId ? { ...m, text: m.text + text } : m));
            }
            return [
              ...prev,
              {
                id: assistantMsgId,
                sender: 'assistant',
                text,
                timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
              },
            ];
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

          setMessages((prev) => {
            // final_answer is authoritative - the generate node strips
            // fabricated citations and thinking tags after the raw tokens
            // were already streamed, so the displayed text is replaced here.
            const existing = prev.some((m) => m.id === assistantMsgId);
            if (!existing) {
              return [
                ...prev,
                {
                  id: assistantMsgId,
                  sender: 'assistant',
                  text: data.final_answer,
                  timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
                  resultData: result,
                },
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
          text: `**An error occurred:**\n${error?.message || 'Server connection failed. Please try again.'}`,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ]);
    } finally {
      setIsQuerying(false);
    }
  };

  return (
    // Extra bottom clearance on mobile only: VersionBadge and VisitorCounter
    // are fixed to the viewport's bottom corners, and on a phone this column
    // fills the viewport exactly, so without it they sat on top of the
    // disclaimer's last line instead of beside the card.
    <div className="max-w-7xl mx-auto px-2 sm:px-4 pt-4 pb-10 sm:pb-4 h-full flex flex-col lg:flex-row gap-4 overflow-hidden">

      {/* Backdrop for the mobile drawer only - desktop never sets
          isSidebarOpen, so this never mounts there. */}
      {isSidebarOpen && (
        <div
          className="fixed top-16 inset-x-0 bottom-0 z-40 bg-black/50 backdrop-blur-sm lg:hidden"
          onClick={() => setIsSidebarOpen(false)}
        />
      )}

      {/* Left Sidebar. A permanent column on lg+; below that, a slide-over
          drawer (fixed, off-canvas by default, translated in over the
          conversation) instead of a stacked column - stacking left so little
          height for the conversation that it was unusable. */}
      <div
        className={`fixed top-16 bottom-0 left-0 z-50 w-[82vw] max-w-[320px] lg:static lg:top-auto lg:z-auto lg:w-80 lg:max-w-none
          glass rounded-r-3xl lg:rounded-3xl p-4 flex flex-col justify-between shrink-0 overflow-y-auto
          transition-transform duration-300 ease-out lg:translate-x-0
          ${isSidebarOpen ? 'translate-x-0' : '-translate-x-full'}`}
      >

        <div className="space-y-4">
          {/* The panel used to open with "Academic Chatbot / Verified RAG
              Assistant" beside a chat glyph. The navbar says who this is one
              line above, and the chat panel said it a third time, so all that
              survives here is what a visitor can act on. */}
          <div className="flex items-center gap-2 border-b border-accent-500/10 pb-3">
            <button
              onClick={() => { handleNewChat(); setIsSidebarOpen(false); }}
              title="Start a new conversation"
              className="flex-1 px-3 py-2 glass-well hover:bg-accent-600 text-[var(--text-secondary)] hover:text-white rounded-xl transition-all cursor-pointer flex items-center justify-center gap-1.5 text-xs font-bold"
            >
              <Plus className="w-4 h-4" />
              <span>New conversation</span>
            </button>
            {/* Closes the drawer; a permanent column on lg+ has nothing to
                close, so this button only exists below that breakpoint. */}
            <button
              onClick={() => setIsSidebarOpen(false)}
              title="Close menu"
              className="lg:hidden p-2 glass-well text-[var(--text-muted)] hover:text-[var(--text)] rounded-xl transition-colors cursor-pointer"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          <div className="glass-well rounded-2xl p-3 space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="font-bold text-[var(--text-secondary)] flex items-center space-x-1.5">
                <Layers className="w-3.5 h-3.5 text-accent-500 dark:text-accent-400" />
                <span>Knowledge Base</span>
              </span>
              <span className="bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20 px-2.5 py-0.5 rounded-full font-mono text-[11px] font-extrabold">
                Live
              </span>
            </div>
            <p className="text-xs text-[var(--text-muted)] leading-normal">
              Course handbooks, exam regulations, and official programme documents.
            </p>
          </div>

          <div className="space-y-2">
            <span className="text-[11px] font-extrabold text-accent-500 dark:text-accent-400 uppercase tracking-wider block px-1">
              Quick Academic Queries
            </span>
            {/* No height cap: every topic is listed, and the sidebar itself is
                what scrolls when they do not all fit. A cap here showed only
                the first seven and hid the rest behind a second scrollbar. */}
            {/* One compact line each. The two-line layout with a boxed icon
                came to ~62px per row, so only half the list could ever be on
                screen at once; the category now rides on the same line as the
                title instead of costing a row of its own. */}
            <div className="space-y-1">
              {ACADEMIC_TOPICS.map((topic, idx) => {
                const Icon = topic.icon;
                return (
                  <button
                    key={idx}
                    onClick={() => { handleRunQuery(topic.query); setIsSidebarOpen(false); }}
                    disabled={isQuerying}
                    title={topic.query}
                    className="w-full glass-well hover:bg-[var(--bg-inset)]/80 hover:border-accent-500/40 px-2.5 py-1.5 rounded-xl text-left transition-all group flex items-center gap-2 cursor-pointer"
                  >
                    <Icon className="w-4 h-4 text-accent-500 dark:text-accent-400 shrink-0" />
                    <span className="text-[13px] font-bold text-[var(--text-secondary)] group-hover:text-accent-500 dark:group-hover:text-accent-300 transition-colors truncate">
                      {topic.title}
                    </span>
                    <span className="ml-auto text-[10px] text-[var(--text-faint)] uppercase tracking-wide shrink-0 hidden lg:inline">
                      {topic.badge}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {/* The session identity that used to sit here is gone. It is still
            shown under the message box, so repeating it took sidebar height
            from the topic list for no added information. Only the admin
            shortcut remains, and only for admins. */}
        {isAdmin && onOpenAdminMode && (
          <div className="pt-3 border-t border-accent-500/10">
            <button
              onClick={() => { onOpenAdminMode(); setIsSidebarOpen(false); }}
              className="w-full bg-amber-500/20 text-amber-600 dark:text-amber-300 border border-amber-500/30 text-[11px] font-extrabold px-3 py-2 rounded-2xl hover:bg-amber-500/30 transition-all cursor-pointer"
            >
              Admin Panel
            </button>
          </div>
        )}

      </div>

      {/* Main Chat Conversation Window. min-h-0 lets it shrink below its
          content height, which is what allows the message list inside to
          scroll instead of stretching the page. */}
      <div className="flex-1 min-h-0 glass rounded-3xl flex flex-col justify-between overflow-hidden relative">

        {/* No header here on lg+. It restated the assistant's name and
            tagline a third time and cost 69px of an 800px window, and its
            one real control (clear the thread) does the same thing as the
            sidebar's New conversation button. The green "Online" dot went
            with it: it was hard-coded, so it claimed a status nothing ever
            checked.

            Below lg, the sidebar is a drawer rather than a visible column,
            so this bar is the only way to reach it - without it, "Quick
            Academic Queries" and the Knowledge Base panel would be
            unreachable on a phone. */}
        <div className="lg:hidden flex items-center gap-2 px-4 pt-3.5 shrink-0">
          <button
            onClick={() => setIsSidebarOpen(true)}
            title="Quick queries and knowledge base"
            className="p-2 glass-well text-[var(--text-secondary)] hover:text-accent-500 dark:hover:text-accent-400 rounded-xl transition-colors cursor-pointer"
          >
            <Menu className="w-4 h-4" />
          </button>
          <span className="text-[11px] font-extrabold text-[var(--text-muted)] uppercase tracking-wider">
            Quick queries
          </span>
        </div>

        <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-6">

          {/* An empty message would render as a padded, blank bubble. That
              happens for the moment before the greeting starts typing, and it
              reads as a rendering glitch rather than as anticipation. */}
          {messages.filter((msg) => msg.text.length > 0).map((msg) => {
            const isUser = msg.sender === 'user';
            return (
              <div key={msg.id} className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
                {/* Neither an avatar nor a name-and-time line above the
                    bubble. In a conversation with exactly two participants,
                    the side a bubble sits on and its colour say who spoke;
                    everything else was the same fact repeated. The clock was
                    the weakest of them - every message in a session carries
                    nearly the same minute, so a column of "17:35" told nobody
                    anything.

                    Both survive where they cost nothing: the speaker as text
                    only a screen reader sees, since alignment and colour do
                    not exist for one, and the time as a tooltip for the rare
                    moment someone wants it. */}
                <div className={`max-w-[88%] sm:max-w-[80%] ${isUser ? 'items-end' : 'items-start'}`}>
                  <div
                    title={`${isUser ? email || 'You' : 'Academic Assistant'} at ${msg.timestamp}`}
                    className={`rounded-2xl p-4 sm:p-5 text-xs sm:text-sm leading-relaxed shadow-xl ${
                      isUser
                        ? 'bg-gradient-to-r from-accent-600 to-accent-700 text-white rounded-tr-sm border border-accent-400/30 shadow-accent-600/20'
                        : 'glass-well text-[var(--text)] rounded-tl-sm space-y-3'
                    }`}
                  >
                    <span className="sr-only">
                      {isUser ? email || 'You' : 'Academic Assistant'} said:
                    </span>
                    {isUser ? (
                      <p className="whitespace-pre-wrap font-medium">{msg.text}</p>
                    ) : (
                      <>
                        {msg.resultData?.hasExpiredDeadline && (
                          <div className="flex items-center gap-1.5 text-[10px] sm:text-[11px] font-bold text-amber-600 dark:text-amber-400 bg-amber-500/10 border border-amber-500/20 rounded-xl px-2.5 py-1.5">
                            <FileWarning className="w-3.5 h-3.5 shrink-0" />
                            <span>Mentions a deadline that has already passed</span>
                          </div>
                        )}
                        <div className="answer-prose max-w-none text-xs sm:text-sm text-[var(--text-secondary)]">
                          <ReactMarkdown remarkPlugins={[remarkGfm]} components={ANSWER_MARKDOWN_COMPONENTS}>{msg.text}</ReactMarkdown>
                        </div>
                      </>
                    )}

                    {!isUser && msg.resultData && (
                      <div className="pt-3.5 border-t border-accent-500/10 space-y-3">

                        <div className="flex flex-wrap items-center justify-between gap-2 text-[10px] text-[var(--text-muted)] font-mono">
                          <div className="flex flex-wrap items-center gap-1.5">
                            {/* Far left, opposite the controls. It is
                                information about the answer, not an action on
                                it, so it belongs with the other read-only
                                markers rather than crowding the buttons.
                                Reported once when the answer lands rather than
                                counted up during the wait: a ticking number is
                                one more thing to watch and nothing you can act
                                on. */}
                            {msg.resultData.elapsedMs > 0 && (
                              <span
                                className="flex items-center space-x-1 bg-[var(--bg-muted)] px-2.5 py-1 rounded-xl border border-accent-500/15 text-[var(--text-muted)]"
                                title={`This answer took ${(msg.resultData.elapsedMs / 1000).toFixed(1)} seconds`}
                              >
                                <Timer className="w-3 h-3" />
                                <span className="font-mono tabular-nums">
                                  {formatElapsed(msg.resultData.elapsedMs)}
                                </span>
                              </span>
                            )}
                            {/* Admin-only, same reasoning as the cached badge
                                below: per-node timings name internal graph
                                stages (retrieve, generate, detect_contribution)
                                that mean nothing to a student, and a slow one
                                reads as a fault rather than as the normal cost
                                of a local model. */}
                            {isAdmin && Object.entries(msg.resultData.nodeLatencies || {}).map(([node, ms]) => (
                              <span key={node} className="bg-[var(--bg-muted)] border border-accent-500/15 px-2.5 py-1 rounded-xl text-[var(--text-secondary)] flex items-center space-x-1">
                                <Zap className="w-3 h-3 text-emerald-600 dark:text-emerald-400" />
                                <span>{node}: {Math.round(ms)}ms</span>
                              </span>
                            ))}
                            {/* Admin-only: where an answer came from is an
                                operational detail. To a student it invites the
                                wrong question - whether a "cached" answer is
                                somehow less current than a fresh one - when in
                                fact it is the reviewed, approved wording and
                                if anything more trustworthy. */}
                            {isAdmin && msg.resultData.cached && (
                              <span className="bg-accent-500/10 text-accent-600 dark:text-accent-300 border border-accent-500/20 px-2.5 py-1 rounded-xl font-bold">
                                cached
                              </span>
                            )}
                            {msg.resultData.autoFlaggedContribution && (
                              <span className="bg-amber-500/10 text-amber-600 dark:text-amber-300 border border-amber-500/20 px-2.5 py-1 rounded-xl font-bold">
                                Flagged: {msg.resultData.autoFlaggedContribution}
                              </span>
                            )}
                          </div>

                          <div className="flex items-center gap-1.5">
                            {msg.resultData.queryLogId != null && (
                              <div className="flex items-center gap-1 bg-[var(--bg-muted)] px-1.5 py-1 rounded-xl border border-accent-500/15">
                                <button
                                  onClick={() => handleRate(msg.id, msg.resultData!.queryLogId!, 1)}
                                  title="This answer was helpful"
                                  className={`p-0.5 rounded-lg transition-colors cursor-pointer ${
                                    ratings[msg.id] === 1
                                      ? 'text-emerald-600 dark:text-emerald-400'
                                      : 'text-[var(--text-muted)] hover:text-emerald-500'
                                  }`}
                                >
                                  <ThumbsUp className="w-3.5 h-3.5" />
                                </button>
                                <button
                                  onClick={() => handleRate(msg.id, msg.resultData!.queryLogId!, -1)}
                                  title="This answer was wrong or unhelpful"
                                  className={`p-0.5 rounded-lg transition-colors cursor-pointer ${
                                    ratings[msg.id] === -1
                                      ? 'text-rose-600 dark:text-rose-400'
                                      : 'text-[var(--text-muted)] hover:text-rose-500'
                                  }`}
                                >
                                  <ThumbsDown className="w-3.5 h-3.5" />
                                </button>
                              </div>
                            )}

                            <button
                              onClick={() => handleCopy(msg.text, msg.id)}
                              className="hover:text-[var(--text)] flex items-center space-x-1 bg-[var(--bg-muted)] px-2.5 py-1 rounded-xl border border-accent-500/15 transition-colors cursor-pointer"
                            >
                              {copiedId === msg.id ? (
                                <>
                                  <Check className="w-3 h-3 text-emerald-600 dark:text-emerald-400" />
                                  <span className="text-emerald-600 dark:text-emerald-400 font-bold">Copied</span>
                                </>
                              ) : (
                                <>
                                  <Copy className="w-3 h-3 text-[var(--text-muted)]" />
                                  <span>Copy</span>
                                </>
                              )}
                            </button>
                          </div>
                        </div>

                        {msg.resultData.retrieval.length > 0 && (
                          <div className="space-y-2 pt-1">
                            <button
                              onClick={() => setExpandedCitationsMsgId(expandedCitationsMsgId === msg.id ? null : msg.id)}
                              className="w-full flex items-center justify-between text-[11px] font-bold text-accent-600 dark:text-accent-300 hover:text-accent-500 dark:hover:text-accent-200 bg-[var(--bg-muted)] p-2.5 rounded-2xl border border-accent-500/20 cursor-pointer transition-all shadow-sm"
                            >
                              <span className="flex items-center space-x-2">
                                <FileText className="w-3.5 h-3.5 text-accent-500 dark:text-accent-400" />
                                <span>Verified Document Passages Used ({msg.resultData.retrieval.length})</span>
                              </span>
                              {expandedCitationsMsgId === msg.id ? (
                                <ChevronDown className="w-3.5 h-3.5 text-[var(--text-muted)]" />
                              ) : (
                                <ChevronRight className="w-3.5 h-3.5 text-[var(--text-muted)]" />
                              )}
                            </button>

                            {expandedCitationsMsgId === msg.id && (
                              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 animate-in fade-in duration-150 pt-1">
                                {msg.resultData.retrieval.map((item, idx) => (
                                  <div
                                    key={idx}
                                    onClick={() => setSelectedChunk(item)}
                                    className="bg-[var(--bg-muted)] hover:bg-[var(--bg-inset)] border border-accent-500/15 hover:border-accent-500/40 p-3 rounded-2xl cursor-pointer transition-all space-y-1 text-[11px] shadow-sm"
                                  >
                                    <div className="flex items-center justify-between font-bold text-accent-600 dark:text-accent-300 truncate">
                                      <span className="truncate">{item.source_id}</span>
                                      {item.rerank_score != null && (
                                        <span className="text-[9px] bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 px-2 py-0.5 rounded-full font-mono font-black shrink-0 ml-1">
                                          {item.rerank_score.toFixed(2)}
                                        </span>
                                      )}
                                    </div>
                                    {item.expired_since && (
                                      <div className="flex items-center gap-1 text-[9px] font-bold text-amber-600 dark:text-amber-400">
                                        <FileWarning className="w-3 h-3 shrink-0" />
                                        <span>Outdated since {item.expired_since}</span>
                                      </div>
                                    )}
                                    <p className="text-[10px] text-[var(--text-muted)] line-clamp-2 font-mono leading-relaxed">
                                      "{item.snippet}"
                                    </p>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        )}

                        {/* Brass, not amber: this invites an action, it does
                            not warn about anything. Amber now means only
                            "something needs your attention" (the admin queue
                            counts), and a loud yellow bar under every single
                            answer was claiming that meaning on every turn. */}
                        <div className="flex items-center justify-between bg-brass-500/10 border border-brass-500/25 p-2.5 rounded-2xl text-[10px] text-brass-800 dark:text-brass-200">
                          <span className="font-medium">Notice something outdated or missing?</span>
                          {/* Dark text on brass, not white: at 10px bold,
                              white on brass-500 measures 3.2:1, below AA for
                              text this size. Near-black on the same fill
                              measures 5.5:1. */}
                          <button
                            onClick={() => {
                              setIsSuggestModalOpen(true);
                              setSuggestContent('');
                            }}
                            className="bg-brass-500 hover:bg-brass-400 text-slate-950 font-black px-3 py-1.5 rounded-xl transition-all shrink-0 cursor-pointer flex items-center space-x-1 shadow-sm"
                          >
                            <PlusCircle className="w-3.5 h-3.5" />
                            <span>Notify Admin</span>
                          </button>
                        </div>

                      </div>
                    )}
                  </div>
                </div>
              </div>
            );
          })}

          {isQuerying && <ThinkingIndicator />}

          <div ref={messagesEndRef} />
        </div>

        <div className="glass-strong border-x-0 border-b-0 p-3.5 sm:p-5 space-y-3">

          {/* Wrapping, not a scrolling strip. Every chip used to be clipped at
              20rem AND parked in a horizontally scrolling row, so the only way
              to read a suggestion was to scroll sideways to a chip that was
              still cut off mid-sentence - which defeats the point of offering
              an example question.

              Hidden below sm: on a phone the sidebar's own Quick Academic
              Queries already offers the same one-tap shortcuts, and this
              second copy was costing roughly half the mobile chat card's
              height - the actual conversation, including the welcome
              message, had nowhere left to render. */}
          <div className="hidden sm:block space-y-2">
            <span className="block text-accent-500 dark:text-accent-400 text-[10px] font-extrabold uppercase tracking-wider">
              Suggested Queries:
            </span>
            {/* A grid rather than a wrapping row. Chips sized to their own text
                wrap into whatever shape the sentence lengths happen to produce
                - one per line, then two, with a gap down the middle. Equal
                cells make the block symmetric no matter what the questions
                say, and stretch keeps the two chips in a row the same height
                if one ever does wrap. */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 items-stretch">
              {SUGGESTED_QUERIES.map((sq, idx) => (
                <button
                  key={idx}
                  onClick={() => handleRunQuery(sq)}
                  disabled={isQuerying}
                  className="glass-well hover:bg-[var(--bg-inset)] hover:border-accent-500/40 text-[var(--text-secondary)] hover:text-[var(--text)] px-3.5 py-2 rounded-2xl transition-all text-left text-[11px] cursor-pointer font-semibold"
                >
                  "{sq}"
                </button>
              ))}
            </div>
          </div>

          <div className="relative flex items-center">
            <textarea
              rows={1}
              value={queryInput}
              onChange={(e) => setQueryInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  if (!isQuerying && queryInput.trim()) {
                    handleRunQuery();
                  }
                }
              }}
              placeholder="Ask about program structure, course requirements, or exam deadlines..."
              disabled={isQuerying}
              // pr-14 on mobile, not pr-32: the icon-only button there needs
              // far less clearance, and the placeholder wrapped to a second
              // line under the old, wider reservation - rows={1} never grew
              // to fit it, so that second line sat clipped behind the
              // button instead of being readable.
              //
              // text-base (16px), not text-xs, on mobile: iOS Safari zooms
              // the whole page in on focus for any input whose font-size
              // computes under 16px - that zoom, not a deliberate control,
              // was what made the box "jump". The placeholder keeps the
              // smaller size on its own via the placeholder: variant, which
              // Safari's zoom check does not look at.
              className="w-full glass-well focus:border-accent-500 focus:ring-2 focus:ring-accent-500/20 rounded-2xl pl-4 pr-14 sm:pr-32 py-3.5 text-base sm:text-sm placeholder:text-xs sm:placeholder:text-sm text-[var(--text)] placeholder-[var(--text-faint)] focus:outline-none transition-all resize-none font-medium"
            />

            <button
              onClick={() => handleRunQuery()}
              disabled={isQuerying || !queryInput.trim()}
              title="Submit"
              className="absolute right-2 bg-gradient-to-r from-accent-600 to-accent-700 hover:from-accent-500 hover:to-accent-600 disabled:opacity-40 text-white text-xs font-bold px-2.5 sm:px-4 py-2 rounded-xl flex items-center space-x-1.5 shadow-md transition-all active:scale-95 cursor-pointer border border-accent-400/30"
            >
              {isQuerying ? <RefreshCw className="w-4 h-4 animate-spin" /> : (
                <>
                  <span className="hidden sm:inline">Submit</span>
                  <Send className="w-3.5 h-3.5" />
                </>
              )}
            </button>
          </div>

          {/* Said plainly and before the fact, not buried in a policy page:
              people are entitled to know their questions are kept and read by
              a person, especially while the assistant is still being trained. */}
          <div className="flex items-start gap-2 text-[10px] text-[var(--text-muted)] px-1 leading-relaxed">
            <ShieldCheck className="w-3.5 h-3.5 text-accent-500 dark:text-accent-400 shrink-0 mt-px" />
            <span>
              This assistant is still being trained. Your questions and the answers given are
              stored and reviewed by the programme team so mistakes can be corrected, and an
              approved answer is then reused for anyone who asks the same thing.
              <strong className="text-[var(--text-secondary)]"> Please do not enter personal or
              sensitive information.</strong>
            </span>
          </div>

          {/* A footer used to sit here saying "Press Enter to submit query"
              and naming the session id. Enter-to-send is universal in a chat
              box, and the navbar already shows who you are signed in as, so
              the row told a first-time visitor nothing and a returning one
              less than that. */}

        </div>

      </div>

      {/* Source Chunk Detail Modal */}
      {selectedChunk && (
        <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="glass-strong rounded-2xl max-w-2xl w-full p-6 space-y-4 text-[var(--text)]">
            <div className="flex items-center justify-between border-b border-[var(--border)] pb-3">
              <div>
                <span className="text-[10px] font-bold text-accent-600 dark:text-accent-400 uppercase tracking-wider">Document Chunk Detail</span>
                <h3 className="text-base font-bold text-[var(--text)]">{selectedChunk.source_id}</h3>
              </div>
              <button onClick={() => setSelectedChunk(null)} className="p-1 text-[var(--text-muted)] hover:text-[var(--text)] cursor-pointer">
                <X className="w-5 h-5" />
              </button>
            </div>

            {selectedChunk.expired_since && (
              <div className="flex items-center gap-2 text-xs font-bold text-amber-600 dark:text-amber-400 bg-amber-500/10 border border-amber-500/20 rounded-xl p-3">
                <FileWarning className="w-4 h-4 shrink-0" />
                <span>This source describes a cycle that ended on {selectedChunk.expired_since}. Any dates in it belong to a past cycle.</span>
              </div>
            )}

            <div className="flex items-center space-x-4 text-xs font-mono glass-well p-3 rounded-xl">
              {selectedChunk.rerank_score != null && (
                <div>Rerank score: <strong className="text-emerald-600 dark:text-emerald-400">{selectedChunk.rerank_score.toFixed(3)}</strong></div>
              )}
              {selectedChunk.hybrid_score != null && (
                <div>Hybrid score: <strong className="text-accent-500 dark:text-accent-400">{selectedChunk.hybrid_score.toFixed(4)}</strong></div>
              )}
            </div>

            <div className="space-y-1">
              <span className="text-xs font-semibold text-[var(--text-muted)]">Passage excerpt:</span>
              <div className="glass-well p-4 rounded-xl text-xs font-mono text-[var(--text-secondary)] leading-relaxed max-h-60 overflow-y-auto whitespace-pre-wrap">
                {selectedChunk.snippet}
              </div>
            </div>

            <div className="flex justify-end pt-2">
              <button onClick={() => setSelectedChunk(null)} className="bg-accent-600 hover:bg-accent-500 text-white text-xs font-semibold px-4 py-2 rounded-xl cursor-pointer">
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Suggest Knowledge Modal */}
      {isSuggestModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="glass-strong rounded-2xl max-w-xl w-full text-[var(--text)] p-6 space-y-5">
            <div className="flex items-center justify-between border-b border-[var(--border)] pb-4">
              <div className="flex items-center space-x-2">
                <ShieldCheck className="w-5 h-5 text-amber-500 dark:text-amber-400" />
                <h3 className="text-base font-bold text-[var(--text)]">Submit Knowledge for Admin Review</h3>
              </div>
              <button onClick={() => setIsSuggestModalOpen(false)} className="text-[var(--text-muted)] hover:text-[var(--text)] p-1 rounded-lg cursor-pointer">
                <X className="w-5 h-5" />
              </button>
            </div>

            {submitSuccessMsg ? (
              <div className="bg-emerald-500/10 border border-emerald-500/20 text-emerald-600 dark:text-emerald-300 text-xs p-4 rounded-xl flex items-center space-x-3">
                <CheckCircle2 className="w-6 h-6 shrink-0 text-emerald-600 dark:text-emerald-400" />
                <span>{submitSuccessMsg}</span>
              </div>
            ) : (
              <form onSubmit={handleSuggestSubmit} className="space-y-4 text-xs">
                <div className="space-y-1">
                  <label className="font-semibold text-[var(--text-secondary)]">Type</label>
                  <select
                    value={suggestType}
                    onChange={(e) => setSuggestType(e.target.value as 'new_info' | 'correction')}
                    className="w-full glass-well rounded-xl p-2.5 text-[var(--text)] focus:outline-none focus:border-accent-500"
                  >
                    <option value="new_info">New information</option>
                    <option value="correction">Correction to existing content</option>
                  </select>
                </div>

                <div className="space-y-1">
                  <label className="font-semibold text-[var(--text-secondary)]">Related document / topic (source id)</label>
                  <input
                    type="text"
                    value={suggestSourceId}
                    onChange={(e) => setSuggestSourceId(e.target.value)}
                    placeholder="e.g. AEDS_website_exams_regulations"
                    className="w-full glass-well rounded-xl p-2.5 text-[var(--text)] placeholder-[var(--text-faint)] focus:outline-none focus:border-accent-500"
                  />
                </div>

                <div className="space-y-1">
                  <label className="font-semibold text-[var(--text-secondary)]">Fact / knowledge content</label>
                  <textarea
                    rows={4}
                    value={suggestContent}
                    onChange={(e) => setSuggestContent(e.target.value)}
                    placeholder="e.g. Econometrics II resit exam will take place on Dec 12 at 14:00 in Room 402."
                    className="w-full glass-well rounded-xl p-2.5 text-[var(--text)] placeholder-[var(--text-faint)] focus:outline-none focus:border-accent-500"
                    required
                  />
                </div>

                <div className="flex justify-end space-x-2 pt-2">
                  <button
                    type="button"
                    onClick={() => setIsSuggestModalOpen(false)}
                    className="px-4 py-2 bg-[var(--bg-inset)] hover:bg-[var(--bg-inset)]/70 text-[var(--text-secondary)] rounded-xl font-medium cursor-pointer"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={isSubmittingKnowledge}
                    className="px-5 py-2 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold rounded-xl transition-all cursor-pointer"
                  >
                    {isSubmittingKnowledge ? 'Submitting...' : 'Submit for Admin Review'}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}

    </div>
  );
};
