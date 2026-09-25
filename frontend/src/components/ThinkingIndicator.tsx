import React from 'react';

/* Shown between sending a question and the first token arriving.

   Three dots in a small pill, and nothing else. Earlier versions ran a
   spinning glyph in an avatar, a spinning refresh icon and bouncing dots all
   at once, then a calmer pill that still narrated itself with "Searching the
   programme documents" and an elapsed-seconds counter. The words earned their
   place less each time you saw them: the pill already appears exactly where
   the answer will, on the assistant's side of the conversation, so its meaning
   is obvious after the first question and the sentence just adds something to
   read while waiting.

   The label survives as aria-label. Dropping visible text must not drop the
   accessible name, or a screen reader is left announcing an empty live region.

   Worth knowing if long waits ever become a complaint: an answer takes about
   thirty seconds on the local model and up to ninety when several people ask
   at once, and there is now nothing on screen that distinguishes second five
   from second eighty. The counter that used to appear after eight seconds is
   what covered that, and it can come back without disturbing this. */

export const ThinkingIndicator: React.FC = () => (
  <div className="flex justify-start">
    <div
      className="glass-well rounded-2xl rounded-tl-sm px-4 py-3 flex items-center gap-1.5"
      role="status"
      aria-live="polite"
      aria-label="Searching the programme documents"
    >
      {[0, 1, 2].map((index) => (
        <span
          key={index}
          aria-hidden
          className="thinking-dot w-1.5 h-1.5 rounded-full bg-accent-500 dark:bg-accent-400"
          style={{ animationDelay: `${index * 0.18}s` }}
        />
      ))}
    </div>
  </div>
);
