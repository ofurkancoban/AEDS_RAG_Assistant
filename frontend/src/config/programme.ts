import type { LucideIcon } from 'lucide-react';
import {
  CalendarClock, ClipboardCheck, Languages, PieChart, ListChecks,
  CalendarRange, Globe, UserSearch, ScrollText, GraduationCap,
  FileWarning, Stethoscope, Mail, Briefcase, BadgeCheck,
  RefreshCcw, PauseCircle, PlaneLanding, Dumbbell, Wallet, TrainFront, Library,
  Home, Euro, UtensilsCrossed, LifeBuoy, Landmark, Building2,
} from 'lucide-react';
import type { Lang } from '../i18n';

/* Everything the student-facing interface knows about the programme it
   serves lives in this one file: its name, the domains questions are filed
   under, the topic shortcuts and the start-screen questions, and which
   documents belong to which domain.

   That is the seam for scaling. The assistant currently serves one
   programme; serving another (or the whole university) means adding a
   second config like this one and a way to pick it, not redesigning the
   interface. Every question listed here has been run through the real
   pipeline, in both languages, and answers from the documents - a shortcut
   that lands in a content gap is worse than no shortcut. */

export type DomainId = 'programme' | 'university' | 'city';

/** Reader-facing text in each interface language. */
export interface Localized {
  en: string;
  de: string;
}

const L = (en: string, de: string): Localized => ({ en, de });

interface TopicConfig {
  title: Localized;
  query: Localized;
  icon: LucideIcon;
}

interface DomainConfig {
  id: DomainId;
  label: Localized;
  description: Localized;
  icon: LucideIcon;
  /** Shown on the start screen's domain card. */
  starters: Localized[];
  topics: TopicConfig[];
}

export interface ProgrammeConfig {
  name: string;
  shortName: string;
  degree: string;
  university: string;
  city: string;
  domains: DomainConfig[];
  /** Maps a retrieved document to the domain it answers for. First match
      wins; anything unmatched belongs to the programme. */
  sourceDomains: { pattern: RegExp; domain: DomainId }[];
  /** How each document is named to a reader, keyed by its source id (the
      file stem in data/documents). Unlisted documents get a name derived
      from the id. */
  sources: Record<string, { title: Localized; kind: Localized }>;
}

/* Kinds repeat across documents, so each is written once. */
const KIND = {
  programmeWebsite: L('Programme website', 'Studiengangswebsite'),
  universityWebsite: L('University website', 'Universitätswebsite'),
  programmeDocument: L('Programme document', 'Studiengangsdokument'),
  regulations: L('Regulations', 'Ordnung'),
  accreditation: L('Accreditation', 'Akkreditierung'),
  studierendenwerk: L('Studierendenwerk', 'Studierendenwerk'),
};

const SEMESTER_FEE = L(
  'How much is the semester contribution and what does it include?',
  'Wie hoch ist der Semesterbeitrag und was ist darin enthalten?',
);
const SEMESTER_TICKET = L(
  'How do I get the Deutschland semester ticket?',
  'Wie bekomme ich das Deutschlandsemesterticket?',
);
const LIBRARY_WEEKEND = L(
  'When is the university library open on weekends?',
  'Wann ist die Universitätsbibliothek am Wochenende geöffnet?',
);
const HOUSING_APPLY = L(
  'How do I apply for student accommodation with the Studierendenwerk?',
  'Wie bewerbe ich mich beim Studierendenwerk für einen Wohnheimplatz?',
);
const HOUSING_RENT = L(
  'How much does a room in a Studierendenwerk residence cost?',
  'Wie viel kostet ein Zimmer in einem Wohnheim des Studierendenwerks?',
);
const HOUSING_NONE = L(
  "What can I do if I don't get a place in student housing?",
  'Was kann ich tun, wenn ich keinen Wohnheimplatz bekomme?',
);

export const PROGRAMME: ProgrammeConfig = {
  name: 'Applied Economics & Data Science',
  shortName: 'AEDS',
  degree: 'M.Sc.',
  university: 'Universität Oldenburg',
  city: 'Oldenburg',
  domains: [
    {
      id: 'programme',
      label: L('Programme', 'Studiengang'),
      description: L('Admission, curriculum, exams, thesis', 'Zulassung, Studienplan, Prüfungen, Masterarbeit'),
      icon: GraduationCap,
      starters: [
        L('What are the application deadlines?', 'Was sind die Bewerbungsfristen?'),
        L('Which courses are compulsory?', 'Welche Kurse sind Pflichtkurse?'),
        L('What are the rules for the Master Thesis?', 'Welche Regeln gelten für die Masterarbeit?'),
      ],
      topics: [
        {
          title: L('Application deadlines', 'Bewerbungsfristen'),
          query: L(
            'What are the application deadlines for Non-EU, EU, and German applicants?',
            'Was sind die Bewerbungsfristen für Bewerber aus Nicht-EU-Ländern, aus der EU und aus Deutschland?',
          ),
          icon: CalendarClock,
        },
        {
          title: L('Admission requirements', 'Zulassungsvoraussetzungen'),
          query: L(
            "How many ECTS credits must an applicant's prior Bachelor's degree be worth, and how many in Economics, Statistics, and Econometrics?",
            'Wie viele ECTS muss der vorherige Bachelorabschluss umfassen, und wie viele davon in Volkswirtschaftslehre, Statistik und Ökonometrie?',
          ),
          icon: ClipboardCheck,
        },
        {
          title: L('Language requirements', 'Sprachvoraussetzungen'),
          query: L('What are the language requirements for admission?', 'Welche Sprachkenntnisse werden für die Zulassung verlangt?'),
          icon: Languages,
        },
        {
          title: L('ECTS distribution', 'Verteilung der ECTS'),
          query: L(
            'How are the 120 ECTS distributed across semesters and subject areas?',
            'Wie verteilen sich die 120 ECTS auf die Semester und Fachgebiete?',
          ),
          icon: PieChart,
        },
        {
          title: L('Compulsory courses', 'Pflichtkurse'),
          query: L('Which courses are compulsory?', 'Welche Kurse sind Pflichtkurse?'),
          icon: ListChecks,
        },
        {
          title: L('First semester plan', 'Plan für das erste Semester'),
          query: L(
            'Which compulsory courses are usually taken in the first semester?',
            'Welche Pflichtkurse belegt man normalerweise im ersten Semester?',
          ),
          icon: CalendarRange,
        },
        {
          title: L('German-taught courses', 'Kurse auf Deutsch'),
          query: L('Which courses are taught only in German?', 'Welche Kurse werden nur auf Deutsch unterrichtet?'),
          icon: Globe,
        },
        // Returns the whole roster grouped by professor. Verified against the
        // Course table: 36 of 37 course-to-professor pairs correct, none wrong.
        {
          title: L('Teaching staff', 'Lehrende'),
          query: L(
            'Which professors teach on this programme, and which courses do they teach?',
            'Welche Professorinnen und Professoren lehren in diesem Studiengang, und welche Kurse unterrichten sie?',
          ),
          icon: UserSearch,
        },
        {
          title: L('Master thesis rules', 'Regeln zur Masterarbeit'),
          query: L(
            'What are the rules for writing, extending, and submitting the Master Thesis?',
            'Welche Regeln gelten für das Schreiben, die Verlängerung und die Abgabe der Masterarbeit?',
          ),
          icon: ScrollText,
        },
        {
          title: L('Thesis credits & grading', 'Masterarbeit: ECTS und Bewertung'),
          query: L(
            'How many ECTS is the thesis module worth, and how long does grading take after submission?',
            'Wie viele ECTS hat das Modul Masterarbeit, und wie lange dauert die Bewertung nach der Abgabe?',
          ),
          icon: GraduationCap,
        },
        {
          title: L('Retaking a failed exam', 'Prüfung wiederholen'),
          query: L(
            'How many times can I retake a failed module exam?',
            'Wie oft kann ich eine nicht bestandene Modulprüfung wiederholen?',
          ),
          icon: FileWarning,
        },
        {
          title: L('Illness on exam day', 'Krank am Prüfungstag'),
          query: L(
            "What should I do if I'm ill on the day of an exam?",
            'Was muss ich tun, wenn ich am Tag einer Prüfung krank bin?',
          ),
          icon: Stethoscope,
        },
        {
          title: L('Examinations office', 'Prüfungsamt'),
          query: L('Who is the contact person at the examinations office?', 'Wer ist die Ansprechperson im Prüfungsamt?'),
          icon: Mail,
        },
        {
          title: L('Career prospects', 'Berufsperspektiven'),
          query: L(
            'What kind of employers hire graduates of this programme?',
            'Welche Arbeitgeber stellen Absolventinnen und Absolventen dieses Studiengangs ein?',
          ),
          icon: Briefcase,
        },
        {
          title: L('Accreditation', 'Akkreditierung'),
          query: L(
            'When does the accreditation for this programme expire?',
            'Wann läuft die Akkreditierung dieses Studiengangs ab?',
          ),
          icon: BadgeCheck,
        },
      ],
    },
    {
      id: 'university',
      label: L('University', 'Universität'),
      description: L('Fees, semester ticket, library, enrolment', 'Beiträge, Semesterticket, Bibliothek, Einschreibung'),
      icon: Landmark,
      starters: [SEMESTER_FEE, SEMESTER_TICKET, LIBRARY_WEEKEND],
      topics: [
        { title: L('Semester fee', 'Semesterbeitrag'), query: SEMESTER_FEE, icon: Wallet },
        {
          title: L('Paying the semester fee', 'Semesterbeitrag bezahlen'),
          query: L('How do I pay the semester fee?', 'Wie bezahle ich den Semesterbeitrag?'),
          icon: Euro,
        },
        { title: L('Semester ticket', 'Semesterticket'), query: SEMESTER_TICKET, icon: TrainFront },
        { title: L('Library opening hours', 'Öffnungszeiten der Bibliothek'), query: LIBRARY_WEEKEND, icon: Library },
        {
          title: L('Re-registration', 'Rückmeldung'),
          query: L('How do I re-register for the next semester?', 'Wie melde ich mich für das nächste Semester zurück?'),
          icon: RefreshCcw,
        },
        {
          title: L('Leave of absence', 'Beurlaubung'),
          query: L('How do I apply for a leave of absence?', 'Wie beantrage ich eine Beurlaubung?'),
          icon: PauseCircle,
        },
        {
          title: L('Arriving as an international student', 'Ankunft als internationale Studierende'),
          query: L(
            'What should I do after arriving in Oldenburg as an international student?',
            'Was sollte ich nach meiner Ankunft in Oldenburg als internationale Studentin oder internationaler Student tun?',
          ),
          icon: PlaneLanding,
        },
        {
          title: L('University sports', 'Hochschulsport'),
          query: L(
            'How much does the university fitness centre cost for students?',
            'Wie viel kostet das Fitnessstudio der Universität für Studierende?',
          ),
          icon: Dumbbell,
        },
      ],
    },
    {
      id: 'city',
      label: L('City & living', 'Stadt & Leben'),
      description: L('Housing, Studierendenwerk, daily life', 'Wohnen, Studierendenwerk, Alltag'),
      icon: Building2,
      starters: [HOUSING_APPLY, HOUSING_RENT, HOUSING_NONE],
      topics: [
        { title: L('Student housing', 'Wohnheime'), query: HOUSING_APPLY, icon: Home },
        { title: L('Rent in residences', 'Mieten im Wohnheim'), query: HOUSING_RENT, icon: Euro },
        {
          title: L('Canteen prices', 'Mensapreise'),
          query: L('How much do meals in the university canteen cost in 2026?', 'Wie viel kosten die Gerichte in der Mensa im Jahr 2026?'),
          icon: UtensilsCrossed,
        },
        { title: L('No place in housing?', 'Kein Wohnheimplatz?'), query: HOUSING_NONE, icon: LifeBuoy },
      ],
    },
  ],
  sourceDomains: [
    { pattern: /enrolment_affairs|international_student|sports_centre|semester_contribution|semester_ticket|library/i, domain: 'university' },
    { pattern: /accommodation|_stw_/i, domain: 'city' },
  ],
  sources: {
    AEDS_website_programme_overview: { title: L('Programme overview', 'Studiengangsübersicht'), kind: KIND.programmeWebsite },
    AEDS_website_how_to_apply: { title: L('How to apply', 'Bewerbung'), kind: KIND.programmeWebsite },
    AEDS_website_application_deadlines_table: { title: L('Application deadlines', 'Bewerbungsfristen'), kind: KIND.programmeWebsite },
    AEDS_website_language_requirements: { title: L('Language requirements', 'Sprachvoraussetzungen'), kind: KIND.programmeWebsite },
    AEDS_website_exams_faq: { title: L('Examinations FAQ', 'FAQ zu Prüfungen'), kind: KIND.programmeWebsite },
    AEDS_website_exams_regulations: { title: L('Examination rules', 'Prüfungsregeln'), kind: KIND.programmeWebsite },
    AEDS_website_theses_faq: { title: L('Master thesis FAQ', 'FAQ zur Masterarbeit'), kind: KIND.programmeWebsite },
    AEDS_accreditation_summary: { title: L('Accreditation summary', 'Zusammenfassung der Akkreditierung'), kind: KIND.accreditation },
    Beschluss_Programmakkreditierung_Applied_Economics_DataScience: {
      title: L('Accreditation decision', 'Akkreditierungsbeschluss'),
      kind: KIND.accreditation,
    },
    MPO_AEDS_2023_EN: { title: L('Examination regulations (2023)', 'Prüfungsordnung (2023)'), kind: KIND.regulations },
    MPO_AEDS_2026_EN: { title: L('Examination regulations (2026)', 'Prüfungsordnung (2026)'), kind: KIND.regulations },
    AEDS_exam_regulations_2026_changes: {
      title: L('Changes in the 2026 regulations', 'Änderungen der Prüfungsordnung 2026'),
      kind: KIND.programmeDocument,
    },
    ZO_FMa_AEDS_EN: { title: L('Admission regulations', 'Zugangs- und Zulassungsordnung'), kind: KIND.regulations },
    SP_MSc_Applied_Economics_and_Data_Science: { title: L('Study plan', 'Studienplan'), kind: KIND.programmeDocument },
    'SP_MSc_Applied-Economics-and-Data-Science': { title: L('Study plan', 'Studienplan'), kind: KIND.programmeDocument },
    'Module_handbook_Applied_Economics_and_Data_Science_Master_Studiengang_SoSe2026_en_GB(3)': {
      title: L('Module handbook (summer 2026)', 'Modulhandbuch (Sommersemester 2026)'),
      kind: KIND.programmeDocument,
    },
    'Master_Applied_Economics_and_Data_Science_UOL_Studiengangsflyer_EN1(1)': {
      title: L('Programme flyer', 'Studiengangsflyer'),
      kind: L('Brochure', 'Broschüre'),
    },
    semester_planning_rules: { title: L('Semester planning rules', 'Regeln zur Semesterplanung'), kind: KIND.programmeDocument },
    catalog: { title: L('Course catalogue', 'Vorlesungsverzeichnis'), kind: L('Catalogue', 'Verzeichnis') },
    AEDS_website_enrolment_affairs: { title: L('Enrolment affairs', 'Studierendenangelegenheiten'), kind: KIND.universityWebsite },
    AEDS_website_international_student_checklist: {
      title: L('International student checklist', 'Checkliste für internationale Studierende'),
      kind: KIND.universityWebsite,
    },
    AEDS_website_sports_centre: {
      title: L('Sports centre prices & hours', 'Hochschulsport: Preise und Zeiten'),
      kind: L('University sports', 'Hochschulsport'),
    },
    AEDS_website_semester_contribution: { title: L('Semester contribution', 'Semesterbeitrag'), kind: KIND.universityWebsite },
    AEDS_website_semester_ticket: {
      title: L('Germany semester ticket', 'Deutschlandsemesterticket'),
      kind: L('Student union (AStA)', 'Studierendenschaft (AStA)'),
    },
    AEDS_website_library_opening_hours: {
      title: L('Library opening hours', 'Öffnungszeiten der Bibliothek'),
      kind: L('University library', 'Universitätsbibliothek'),
    },
    AEDS_website_accommodation: { title: L('Accommodation & living', 'Wohnen & Leben'), kind: KIND.universityWebsite },
    AEDS_website_stw_accommodation: { title: L('Student accommodation', 'Studentisches Wohnen'), kind: KIND.studierendenwerk },
    AEDS_website_stw_faq: { title: L('Student housing FAQ', 'FAQ zum Wohnen'), kind: KIND.studierendenwerk },
    AEDS_website_stw_changes_2026: { title: L('Changes in 2026', 'Änderungen 2026'), kind: KIND.studierendenwerk },
  },
};

/* The programme as one interface language reads it: the same shape with
   plain strings, which is all components ever need. */

export interface Topic {
  title: string;
  query: string;
  icon: LucideIcon;
}

export interface Domain {
  id: DomainId;
  label: string;
  description: string;
  icon: LucideIcon;
  starters: string[];
  topics: Topic[];
}

const domainsByLang = new Map<Lang, Domain[]>();

export function localizedDomains(lang: Lang): Domain[] {
  let domains = domainsByLang.get(lang);
  if (!domains) {
    domains = PROGRAMME.domains.map((d) => ({
      id: d.id,
      label: d.label[lang],
      description: d.description[lang],
      icon: d.icon,
      starters: d.starters.map((s) => s[lang]),
      topics: d.topics.map((t) => ({ title: t.title[lang], query: t.query[lang], icon: t.icon })),
    }));
    domainsByLang.set(lang, domains);
  }
  return domains;
}

export function domainById(id: DomainId, lang: Lang): Domain {
  const domains = localizedDomains(lang);
  return domains.find((d) => d.id === id) ?? domains[0];
}

/** The domain an answer belongs to, judged by its most relevant source
    (retrieval is ordered by rerank score, best first). Answers with no
    documents - structured lookups like the course catalogue - are
    programme answers. */
export function domainForSources(sourceIds: string[]): DomainId {
  if (sourceIds.length === 0) return 'programme';
  const rule = PROGRAMME.sourceDomains.find((r) => r.pattern.test(sourceIds[0]));
  return rule ? rule.domain : 'programme';
}

/* Domain accents: colour carries meaning here (which part of student life a
   question is about) and nothing else. Blue matches the interface accent. */
export const DOMAIN_TONE: Record<DomainId, { dot: string; badge: string; icon: string }> = {
  programme: {
    dot: 'bg-accent-700 dark:bg-accent-400',
    badge: 'text-accent-700 bg-accent-50 border-accent-200 dark:text-accent-200 dark:bg-accent-500/15 dark:border-accent-400/30',
    icon: 'text-accent-700 bg-accent-50 dark:text-accent-200 dark:bg-accent-500/15',
  },
  university: {
    dot: 'bg-teal-700 dark:bg-teal-400',
    badge: 'text-teal-800 bg-teal-50 border-teal-200 dark:text-teal-200 dark:bg-teal-500/15 dark:border-teal-400/30',
    icon: 'text-teal-700 bg-teal-50 dark:text-teal-200 dark:bg-teal-500/15',
  },
  city: {
    dot: 'bg-orange-700 dark:bg-orange-400',
    badge: 'text-orange-800 bg-orange-50 border-orange-200 dark:text-orange-200 dark:bg-orange-500/15 dark:border-orange-400/30',
    icon: 'text-orange-700 bg-orange-50 dark:text-orange-200 dark:bg-orange-500/15',
  },
};
