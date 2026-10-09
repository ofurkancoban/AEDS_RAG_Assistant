import type { LucideIcon } from 'lucide-react';
import {
  CalendarClock, ClipboardCheck, Languages, PieChart, ListChecks,
  CalendarRange, Globe, UserSearch, ScrollText, GraduationCap,
  FileWarning, Stethoscope, Mail, Briefcase, BadgeCheck,
  RefreshCcw, PauseCircle, PlaneLanding, Dumbbell,
  Home, Euro, UtensilsCrossed, LifeBuoy, Landmark, Building2,
} from 'lucide-react';

/* Everything the student-facing interface knows about the programme it
   serves lives in this one file: its name, the domains questions are filed
   under, the topic shortcuts and the start-screen questions, and which
   documents belong to which domain.

   That is the seam for scaling. The assistant currently serves one
   programme; serving another (or the whole university) means adding a
   second config like this one and a way to pick it, not redesigning the
   interface. Every question listed here has been run through the real
   pipeline and answers from the documents - a shortcut that lands in a
   content gap is worse than no shortcut. */

export type DomainId = 'programme' | 'university' | 'city';

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
  /** Shown on the start screen's domain card. */
  starters: string[];
  topics: Topic[];
}

export interface ProgrammeConfig {
  name: string;
  shortName: string;
  degree: string;
  university: string;
  city: string;
  domains: Domain[];
  /** Maps a retrieved document to the domain it answers for. First match
      wins; anything unmatched belongs to the programme. */
  sourceDomains: { pattern: RegExp; domain: DomainId }[];
  /** How each document is named to a reader, keyed by its source id (the
      file stem in data/documents). Unlisted documents get a name derived
      from the id. */
  sources: Record<string, { title: string; kind: string }>;
}

export const PROGRAMME: ProgrammeConfig = {
  name: 'Applied Economics & Data Science',
  shortName: 'AEDS',
  degree: 'M.Sc.',
  university: 'Universität Oldenburg',
  city: 'Oldenburg',
  domains: [
    {
      id: 'programme',
      label: 'Programme',
      description: 'Admission, curriculum, exams, thesis',
      icon: GraduationCap,
      starters: [
        'What are the application deadlines?',
        'Which courses are compulsory?',
        'What are the rules for the Master Thesis?',
      ],
      topics: [
        { title: 'Application deadlines', query: 'What are the application deadlines for Non-EU, EU, and German applicants?', icon: CalendarClock },
        { title: 'Admission requirements', query: "How many ECTS credits must an applicant's prior Bachelor's degree be worth, and how many in Economics, Statistics, and Econometrics?", icon: ClipboardCheck },
        { title: 'Language requirements', query: 'What are the language requirements for admission?', icon: Languages },
        { title: 'ECTS distribution', query: 'How are the 120 ECTS distributed across semesters and subject areas?', icon: PieChart },
        { title: 'Compulsory courses', query: 'Which courses are compulsory?', icon: ListChecks },
        { title: 'First semester plan', query: 'Which compulsory courses are usually taken in the first semester?', icon: CalendarRange },
        { title: 'German-taught courses', query: 'Which courses are taught only in German?', icon: Globe },
        // Returns the whole roster grouped by professor. Verified against the
        // Course table: 36 of 37 course-to-professor pairs correct, none wrong.
        { title: 'Teaching staff', query: 'Which professors teach on this programme, and which courses do they teach?', icon: UserSearch },
        { title: 'Master thesis rules', query: 'What are the rules for writing, extending, and submitting the Master Thesis?', icon: ScrollText },
        { title: 'Thesis credits & grading', query: 'How many ECTS is the thesis module worth, and how long does grading take after submission?', icon: GraduationCap },
        { title: 'Retaking a failed exam', query: 'How many times can I retake a failed module exam?', icon: FileWarning },
        { title: 'Illness on exam day', query: "What should I do if I'm ill on the day of an exam?", icon: Stethoscope },
        { title: 'Examinations office', query: 'Who is the contact person at the examinations office?', icon: Mail },
        { title: 'Career prospects', query: 'What kind of employers hire graduates of this programme?', icon: Briefcase },
        { title: 'Accreditation', query: 'When does the accreditation for this programme expire?', icon: BadgeCheck },
      ],
    },
    {
      id: 'university',
      label: 'University',
      description: 'Enrolment, leave, arrival, sports',
      icon: Landmark,
      starters: [
        'How do I re-register for the next semester?',
        'What should I do after arriving in Oldenburg as an international student?',
        'How much does the university fitness centre cost for students?',
      ],
      topics: [
        { title: 'Re-registration', query: 'How do I re-register for the next semester?', icon: RefreshCcw },
        { title: 'Leave of absence', query: 'How do I apply for a leave of absence?', icon: PauseCircle },
        { title: 'Arriving as an international student', query: 'What should I do after arriving in Oldenburg as an international student?', icon: PlaneLanding },
        { title: 'University sports', query: 'How much does the university fitness centre cost for students?', icon: Dumbbell },
      ],
    },
    {
      id: 'city',
      label: 'City & living',
      description: 'Housing, Studierendenwerk, daily life',
      icon: Building2,
      starters: [
        'How do I apply for student accommodation with the Studierendenwerk?',
        'How much does a room in a Studierendenwerk residence cost?',
        'What can I do if I don\'t get a place in student housing?',
      ],
      topics: [
        { title: 'Student housing', query: 'How do I apply for student accommodation with the Studierendenwerk?', icon: Home },
        { title: 'Rent in residences', query: 'How much does a room in a Studierendenwerk residence cost?', icon: Euro },
        { title: 'Canteen prices', query: 'How much do meals in the university canteen cost in 2026?', icon: UtensilsCrossed },
        { title: 'No place in housing?', query: "What can I do if I don't get a place in student housing?", icon: LifeBuoy },
      ],
    },
  ],
  sourceDomains: [
    { pattern: /enrolment_affairs|international_student|sports_centre/i, domain: 'university' },
    { pattern: /accommodation|_stw_/i, domain: 'city' },
  ],
  sources: {
    AEDS_website_programme_overview: { title: 'Programme overview', kind: 'Programme website' },
    AEDS_website_how_to_apply: { title: 'How to apply', kind: 'Programme website' },
    AEDS_website_application_deadlines_table: { title: 'Application deadlines', kind: 'Programme website' },
    AEDS_website_language_requirements: { title: 'Language requirements', kind: 'Programme website' },
    AEDS_website_exams_faq: { title: 'Examinations FAQ', kind: 'Programme website' },
    AEDS_website_exams_regulations: { title: 'Examination rules', kind: 'Programme website' },
    AEDS_website_theses_faq: { title: 'Master thesis FAQ', kind: 'Programme website' },
    AEDS_accreditation_summary: { title: 'Accreditation summary', kind: 'Accreditation' },
    Beschluss_Programmakkreditierung_Applied_Economics_DataScience: { title: 'Accreditation decision', kind: 'Accreditation' },
    MPO_AEDS_2023_EN: { title: 'Examination regulations (2023)', kind: 'Regulations' },
    ZO_FMa_AEDS_EN: { title: 'Admission regulations', kind: 'Regulations' },
    SP_MSc_Applied_Economics_and_Data_Science: { title: 'Study plan', kind: 'Programme document' },
    'SP_MSc_Applied-Economics-and-Data-Science': { title: 'Study plan', kind: 'Programme document' },
    'Module_handbook_Applied_Economics_and_Data_Science_Master_Studiengang_SoSe2026_en_GB(3)': { title: 'Module handbook (summer 2026)', kind: 'Programme document' },
    'Master_Applied_Economics_and_Data_Science_UOL_Studiengangsflyer_EN1(1)': { title: 'Programme flyer', kind: 'Brochure' },
    semester_planning_rules: { title: 'Semester planning rules', kind: 'Programme document' },
    catalog: { title: 'Course catalogue', kind: 'Catalogue' },
    AEDS_website_enrolment_affairs: { title: 'Enrolment affairs', kind: 'University website' },
    AEDS_website_international_student_checklist: { title: 'International student checklist', kind: 'University website' },
    AEDS_website_sports_centre: { title: 'Sports centre prices & hours', kind: 'University sports' },
    AEDS_website_accommodation: { title: 'Accommodation & living', kind: 'University website' },
    AEDS_website_stw_accommodation: { title: 'Student accommodation', kind: 'Studierendenwerk' },
    AEDS_website_stw_faq: { title: 'Student housing FAQ', kind: 'Studierendenwerk' },
    AEDS_website_stw_changes_2026: { title: 'Changes in 2026', kind: 'Studierendenwerk' },
  },
};

export function domainById(id: DomainId): Domain {
  return PROGRAMME.domains.find((d) => d.id === id) ?? PROGRAMME.domains[0];
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
