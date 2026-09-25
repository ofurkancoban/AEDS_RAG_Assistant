import React from 'react';
import type { Components } from 'react-markdown';

/* Rendering rules shared by every place an assistant answer is displayed.
   react-markdown already refuses raw HTML (no rehype-raw is installed) and
   strips javascript: URLs, so what is left to close is the two things a
   Markdown answer can still do to the reader.

   Images: a Markdown image is fetched by the browser as soon as it renders,
   which turns any URL the model can be made to emit into a silent callback to
   whoever chose it - carrying the reader's IP and anything encoded in the
   query string. The corpus is plain text documents, so a legitimate answer
   never contains an image. Rather than hiding these, the alt text or URL is
   shown as inert text: an admin reviewing a poisoned answer should be able to
   see what was attempted, and a student should not be left wondering why part
   of an answer is blank.

   Links: an answer could carry a link somewhere unrelated to the programme.
   The link still works, but it opens in its own tab and cannot reach back
   into this one through window.opener. */
export const ANSWER_MARKDOWN_COMPONENTS: Components = {
  img: ({ alt, src }) => (
    <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-amber-500/10 text-amber-700 dark:text-amber-300 border border-amber-500/30 text-[0.85em] font-mono">
      image not shown{alt || src ? `: ${alt || src}` : ''}
    </span>
  ),
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noopener noreferrer nofollow">
      {children}
    </a>
  ),
};
