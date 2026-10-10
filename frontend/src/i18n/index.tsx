import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';

/* The student-facing interface in English (the default) or German. Staff
   screens stay English. Answers follow the language of the question on the
   backend, so a German interface with German topic questions gets German
   answers without any extra setting. */

export type Lang = 'en' | 'de';

export const LANGS: { id: Lang; label: string; name: string }[] = [
  { id: 'en', label: 'EN', name: 'English' },
  { id: 'de', label: 'DE', name: 'Deutsch' },
];

const STORAGE_KEY = 'ui_lang';

const en = {
  langSwitch: 'Interface language',

  // Start screen and conversation
  howCanWeHelp: 'How can we help?',
  intro: (city: string) =>
    `Ask about your programme, the university or life in ${city}. Every answer is drawn from official documents and shows its sources.`,
  trustSources: 'Official programme & university sources',
  trustReviewed: 'Answers reviewed by programme staff',
  trustOutdated: 'Outdated sources are flagged',
  fromAssistant: 'From the assistant: ',
  thisConversation: (n: number) => `This conversation · ${n} ${n === 1 ? 'question' : 'questions'}`,
  newQuestion: 'New question',
  followUpPlaceholder: 'Ask a follow-up question',
  answerFailed: '**The answer could not be loaded.**',
  connectionFailed: 'Server connection failed. Please try again.',
  submitted: 'Submitted to the review queue. It will be used once the programme team approves it.',
  submitFailed: 'Failed to submit',

  // Side navigation
  topics: 'Topics',
  closeTopics: 'Close topics',
  openTopics: 'Open topics',
  recent: 'Recent',
  showFewer: 'Show fewer',
  showAll: (n: number) => `Show all ${n}`,
  officialSources: (short: string) => `Official ${short} & university sources`,

  // Composer
  topicKeys: { move: 'move', ask: 'ask', close: 'close' },
  noTopicMatch: (q: string) => `No topic matches "${q}". Press Escape and ask it as a question instead.`,
  browseTopics: 'Browse topics',
  askLabel: 'Ask a question',
  askPlaceholderWide: 'Ask a question, e.g. When is the deadline for the winter semester?',
  askPlaceholder: 'Ask a question…',
  sendQuestion: 'Send question',
  sendTitle: 'Send (Enter)',
  privacyNote: 'Questions and answers are stored and reviewed by the programme team, and are not used to train AI models.',
  privacyWarning: 'Do not enter personal information.',
  keyHints: 'Enter to send · / for topics',

  // Progress
  answerProgress: 'Answer progress',
  stages: {
    understanding: 'Understanding the question',
    searching: 'Searching programme and university documents',
    ranking: 'Selecting the most relevant passages',
    writing: 'Writing the answer',
  } as Record<string, string>,

  // Exchange
  you: 'You',
  youAsked: 'You asked: ',
  pastDeadline: 'Mentions a deadline that has already passed',
  answerTook: (s: string) => `This answer took ${s} seconds`,
  sourcesCount: (n: number) => `${n} ${n === 1 ? 'source' : 'sources'}`,
  instant: 'instant',
  flagged: 'Flagged',
  helpfulLabel: 'This answer was helpful',
  helpful: 'Helpful',
  unhelpfulLabel: 'This answer was wrong or unhelpful',
  downvoteThanks: 'Thanks. The programme team has been notified and will check this answer.',
  copyAnswer: 'Copy answer',
  copy: 'Copy',
  copied: 'Copied',
  suggestTitle: 'Something wrong or outdated? Suggest a correction',
  suggestCorrection: 'Suggest a correction',

  // Sources and evidence
  sources: 'Sources',
  citedOf: (cited: number, total: number) => `${cited} of ${total} cited`,
  relevanceLabel: (pct: number) => `Relevance ${pct} percent`,
  relevance: 'relevance',
  outdated: 'Outdated',
  outdatedSince: (date: string) => `Outdated since ${date}`,
  evidence: 'Evidence',
  sourcesFor: (q: string) => `Sources for “${q}”`,
  sourcesOfSelected: 'Sources of the selected answer',
  noDocuments: 'No documents behind this answer',
  noDocumentsBody:
    'It came from a structured lookup (course catalogue, deadlines table) or the documents did not cover it.',
  sourcesAppear: 'Sources appear here',
  sourcesAppearBody: 'Ask a question and the passages the answer was drawn from will be listed here, with their quoted text.',
  citedTimes: (n: number) => `cited ${n}×`,
  retrievedNotCited: 'retrieved, not cited',
  retrieved: 'retrieved',
  somethingWrong: 'Something wrong or outdated?',
  sourceN: (n: number) => `Source ${n}`,
  clickToShow: 'Click to show this source',

  // Passage and suggestion dialogs
  referencedPassage: 'Referenced passage',
  pastCycle: (date: string) =>
    `This source describes a cycle that ended on ${date}. Any dates in it belong to a past cycle.`,
  rerankScore: 'Rerank score',
  hybridScore: 'Hybrid score',
  excerpt: 'Excerpt',
  reviewQueue: 'Reviewed by the programme team',
  suggestIntro:
    "Nothing you submit reaches the assistant's answers until the programme team has reviewed and approved it.",
  type: 'Type',
  newInformation: 'New information',
  correction: 'Correction',
  relatedDocument: 'Related document or topic',
  relatedPlaceholder: 'e.g. AEDS_website_exams_regulations',
  whatToKnow: 'What should the assistant know?',
  whatToKnowPlaceholder: 'e.g. The Econometrics II resit exam takes place on Dec 12 at 14:00 in Room 402.',
  cancel: 'Cancel',
  submitting: 'Submitting...',
  submitForReview: 'Submit for review',
  close: 'Close',

  // Header and footer
  studentAssistant: 'Student Assistant',
  programme: 'Programme',
  passagesIndexed: (n: string) => `${n} passages indexed`,
  logOut: 'Log out',
  staffSignIn: 'Staff sign-in',
  lightTheme: 'Light theme',
  darkTheme: 'Dark theme',
  switchToLight: 'Switch to light theme',
  switchToDark: 'Switch to dark theme',
  whatsNew: "What's new",
  visitorsTitle: 'Unique visitors since launch',

  // Source names derived from a file name
  sourceKinds: {
    website: 'Website',
    document: 'Document',
    brochure: 'Brochure',
    moduleHandbook: 'Module handbook',
    examRegulations: 'Examination regulations',
    programmeFlyer: 'Programme flyer',
  },
  dateLocale: 'en-GB',
};

export type Strings = typeof en;

const de: Strings = {
  langSwitch: 'Sprache der Oberfläche',

  howCanWeHelp: 'Wie können wir helfen?',
  intro: (city) =>
    `Fragen Sie zu Ihrem Studiengang, zur Universität oder zum Leben in ${city}. Jede Antwort stützt sich auf offizielle Dokumente und nennt ihre Quellen.`,
  trustSources: 'Offizielle Quellen von Studiengang und Universität',
  trustReviewed: 'Antworten werden vom Studiengangsteam geprüft',
  trustOutdated: 'Veraltete Quellen werden markiert',
  fromAssistant: 'Vom Assistenten: ',
  thisConversation: (n) => `Dieses Gespräch · ${n} ${n === 1 ? 'Frage' : 'Fragen'}`,
  newQuestion: 'Neue Frage',
  followUpPlaceholder: 'Anschlussfrage stellen',
  answerFailed: '**Die Antwort konnte nicht geladen werden.**',
  connectionFailed: 'Verbindung zum Server fehlgeschlagen. Bitte versuchen Sie es erneut.',
  submitted: 'An die Prüfung übermittelt. Nach der Freigabe durch das Studiengangsteam wird es übernommen.',
  submitFailed: 'Senden fehlgeschlagen',

  topics: 'Themen',
  closeTopics: 'Themen schließen',
  openTopics: 'Themen öffnen',
  recent: 'Zuletzt',
  showFewer: 'Weniger anzeigen',
  showAll: (n) => `Alle ${n} anzeigen`,
  officialSources: (short) => `Offizielle Quellen von ${short} und Universität`,

  topicKeys: { move: 'wählen', ask: 'fragen', close: 'schließen' },
  noTopicMatch: (q) => `Kein Thema passt zu „${q}“. Drücken Sie Escape und stellen Sie es als Frage.`,
  browseTopics: 'Themen durchsuchen',
  askLabel: 'Frage stellen',
  askPlaceholderWide: 'Frage stellen, z. B. Wann ist die Bewerbungsfrist für das Wintersemester?',
  askPlaceholder: 'Frage stellen…',
  sendQuestion: 'Frage senden',
  sendTitle: 'Senden (Enter)',
  privacyNote:
    'Fragen und Antworten werden gespeichert und vom Studiengangsteam geprüft, aber nicht zum Training von KI-Modellen verwendet.',
  privacyWarning: 'Geben Sie keine persönlichen Daten ein.',
  keyHints: 'Enter zum Senden · / für Themen',

  answerProgress: 'Fortschritt der Antwort',
  stages: {
    understanding: 'Frage wird verstanden',
    searching: 'Dokumente von Studiengang und Universität werden durchsucht',
    ranking: 'Die relevantesten Abschnitte werden ausgewählt',
    writing: 'Antwort wird geschrieben',
  },

  you: 'Sie',
  youAsked: 'Ihre Frage: ',
  pastDeadline: 'Nennt eine Frist, die bereits abgelaufen ist',
  answerTook: (s) => `Diese Antwort dauerte ${s} Sekunden`,
  sourcesCount: (n) => `${n} ${n === 1 ? 'Quelle' : 'Quellen'}`,
  instant: 'sofort',
  flagged: 'Markiert',
  helpfulLabel: 'Diese Antwort war hilfreich',
  helpful: 'Hilfreich',
  unhelpfulLabel: 'Diese Antwort war falsch oder nicht hilfreich',
  downvoteThanks: 'Danke. Das Studiengangsteam wurde informiert und prüft diese Antwort.',
  copyAnswer: 'Antwort kopieren',
  copy: 'Kopieren',
  copied: 'Kopiert',
  suggestTitle: 'Etwas falsch oder veraltet? Korrektur vorschlagen',
  suggestCorrection: 'Korrektur vorschlagen',

  sources: 'Quellen',
  citedOf: (cited, total) => `${cited} von ${total} zitiert`,
  relevanceLabel: (pct) => `Relevanz ${pct} Prozent`,
  relevance: 'Relevanz',
  outdated: 'Veraltet',
  outdatedSince: (date) => `Veraltet seit ${date}`,
  evidence: 'Belege',
  sourcesFor: (q) => `Quellen für „${q}“`,
  sourcesOfSelected: 'Quellen der ausgewählten Antwort',
  noDocuments: 'Keine Dokumente zu dieser Antwort',
  noDocumentsBody:
    'Sie stammt aus einer strukturierten Abfrage (Vorlesungsverzeichnis, Fristentabelle) oder die Dokumente deckten die Frage nicht ab.',
  sourcesAppear: 'Hier erscheinen die Quellen',
  sourcesAppearBody:
    'Stellen Sie eine Frage, dann werden hier die Abschnitte aufgeführt, auf die sich die Antwort stützt, mit ihrem Wortlaut.',
  citedTimes: (n) => `${n}× zitiert`,
  retrievedNotCited: 'gefunden, nicht zitiert',
  retrieved: 'gefunden',
  somethingWrong: 'Etwas falsch oder veraltet?',
  sourceN: (n) => `Quelle ${n}`,
  clickToShow: 'Klicken, um diese Quelle anzuzeigen',

  referencedPassage: 'Zitierter Abschnitt',
  pastCycle: (date) =>
    `Diese Quelle beschreibt einen Zeitraum, der am ${date} endete. Alle Daten darin gehören zu einem vergangenen Zeitraum.`,
  rerankScore: 'Relevanzwert',
  hybridScore: 'Suchwert',
  excerpt: 'Auszug',
  reviewQueue: 'Wird vom Studiengangsteam geprüft',
  suggestIntro:
    'Ihre Eingabe fließt erst in die Antworten ein, wenn das Studiengangsteam sie geprüft und freigegeben hat.',
  type: 'Art',
  newInformation: 'Neue Information',
  correction: 'Korrektur',
  relatedDocument: 'Betroffenes Dokument oder Thema',
  relatedPlaceholder: 'z. B. AEDS_website_exams_regulations',
  whatToKnow: 'Was sollte der Assistent wissen?',
  whatToKnowPlaceholder: 'z. B. Die Wiederholungsprüfung Econometrics II findet am 12. Dezember um 14:00 Uhr in Raum 402 statt.',
  cancel: 'Abbrechen',
  submitting: 'Wird gesendet...',
  submitForReview: 'Zur Prüfung senden',
  close: 'Schließen',

  studentAssistant: 'Studierenden-Assistent',
  programme: 'Studiengang',
  passagesIndexed: (n) => `${n} Abschnitte indexiert`,
  logOut: 'Abmelden',
  staffSignIn: 'Team-Anmeldung',
  lightTheme: 'Helles Design',
  darkTheme: 'Dunkles Design',
  switchToLight: 'Zum hellen Design wechseln',
  switchToDark: 'Zum dunklen Design wechseln',
  whatsNew: 'Neuigkeiten',
  visitorsTitle: 'Verschiedene Besucher seit dem Start',

  sourceKinds: {
    website: 'Website',
    document: 'Dokument',
    brochure: 'Broschüre',
    moduleHandbook: 'Modulhandbuch',
    examRegulations: 'Prüfungsordnung',
    programmeFlyer: 'Studiengangsflyer',
  },
  dateLocale: 'de-DE',
};

export const STRINGS: Record<Lang, Strings> = { en, de };

function storedLang(): Lang {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    return value === 'de' || value === 'en' ? value : 'en';
  } catch {
    return 'en';
  }
}

interface I18nValue {
  lang: Lang;
  setLang: (lang: Lang) => void;
  t: Strings;
}

const I18nContext = createContext<I18nValue>({ lang: 'en', setLang: () => {}, t: en });

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState<Lang>(storedLang);

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const value = useMemo<I18nValue>(
    () => ({
      lang,
      t: STRINGS[lang],
      setLang: (next) => {
        setLangState(next);
        try {
          localStorage.setItem(STORAGE_KEY, next);
        } catch {
          // A blocked storage only means the choice is not remembered.
        }
      },
    }),
    [lang]
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nValue {
  return useContext(I18nContext);
}
