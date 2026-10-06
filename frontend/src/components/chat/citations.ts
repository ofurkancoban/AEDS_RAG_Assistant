import { PROGRAMME } from '../../config/programme';
import { Lang, STRINGS } from '../../i18n';

// "[2]" written by the model after a fact (see graph/nodes.py's numbered
// context). A following "(" means a Markdown link, which is left alone.
const MARKER_RE = /\[(\d+)\](?!\()/g;

/** Turns "[2]" into a Markdown link the answer renderer recognises and draws
    as a citation chip; any other link keeps its ordinary rendering. */
export function linkifyCitations(text: string): string {
  return text.replace(MARKER_RE, (_, n) => `[${n}](#cite-${n})`);
}

export function citedNumbers(text: string): Set<number> {
  return new Set([...text.matchAll(MARKER_RE)].map((m) => Number(m[1])));
}

/** How many times each passage number is cited in the answer. */
export function citationCounts(text: string): Map<number, number> {
  const counts = new Map<number, number>();
  for (const m of text.matchAll(MARKER_RE)) {
    const n = Number(m[1]);
    counts.set(n, (counts.get(n) ?? 0) + 1);
  }
  return counts;
}

/** For copying an answer elsewhere, where the numbers would point nowhere. */
export function stripCitations(text: string): string {
  return text.replace(/[ \t]*(?:\[\d+\](?!\())+/g, '');
}

export const CITE_PREFIX = '#cite-';

/** Passages are stored as the Markdown they were ingested from; quoted back
    to a reader they should read as prose, not as "## Heading - **bold**". */
export function plainSnippet(text: string): string {
  return text
    .replace(/^\s{0,3}#{1,6}\s+/gm, '')
    .replace(/\*\*|__/g, '')
    .replace(/(^|\s)[*_](\S[^*_]*\S)[*_](?=\s|[.,;:]|$)/g, '$1$2')
    .replace(/^\s*[-*+]\s+/gm, '• ')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/\|/g, ' ')
    .replace(/[ \t]{2,}/g, ' ')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

/* Source ids are file stems ("AEDS_website_language_requirements"). Readers
   get a title and a kind instead; the raw id stays visible in the passage
   dialog for anyone who needs to find the file. */
export function describeSource(sourceId: string, lang: Lang): { title: string; kind: string } {
  const known = PROGRAMME.sources[sourceId];
  if (known) return { title: known.title[lang], kind: known.kind[lang] };
  const kinds = STRINGS[lang].sourceKinds;
  const humanize = (s: string) => {
    const words = s.replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim();
    return words.charAt(0).toUpperCase() + words.slice(1);
  };
  if (sourceId.startsWith('AEDS_website_')) {
    return { title: humanize(sourceId.slice('AEDS_website_'.length)), kind: kinds.website };
  }
  if (/^MPO_/i.test(sourceId)) return { title: kinds.examRegulations, kind: humanize(sourceId) };
  if (/flyer/i.test(sourceId)) return { title: kinds.programmeFlyer, kind: kinds.brochure };
  if (/handbook|modul/i.test(sourceId)) return { title: humanize(sourceId), kind: kinds.moduleHandbook };
  return { title: humanize(sourceId), kind: kinds.document };
}

/** Rerank scores are probabilities in 0..1; clamp anything odd. */
export function relevance(score: number | null | undefined): number {
  if (score == null || Number.isNaN(score)) return 0;
  return Math.max(0, Math.min(1, score));
}
