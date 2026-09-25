import React from 'react';
import { AlertTriangle } from 'lucide-react';

interface InjectionWarningProps {
  markers?: string[];
}

/* Shown above content awaiting review when it contains patterns aimed at the
   model rather than at a reader.

   Approving is what makes a submission part of the corpus, or an answer the
   reply every later asker receives, so this is the last point at which a
   planted instruction can be caught. The wording deliberately does not say
   "malicious": these patterns also occur innocently, and the reviewer is being
   asked to look, not to reject. */
export const InjectionWarning: React.FC<InjectionWarningProps> = ({ markers }) => {
  if (!markers || markers.length === 0) return null;

  return (
    <div className="rounded-xl border border-amber-500/40 bg-amber-500/10 p-3 space-y-1.5">
      <div className="flex items-center gap-2 text-[11px] font-extrabold text-amber-700 dark:text-amber-300 uppercase tracking-wide">
        <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
        <span>Read this one carefully before approving</span>
      </div>
      <p className="text-[11px] text-[var(--text-secondary)] leading-relaxed">
        This text contains wording that is typically addressed to the assistant
        rather than to a reader. That can be innocent, but approved content is
        treated as authoritative, so check it says only what it claims to say.
      </p>
      <ul className="flex flex-wrap gap-1.5 pt-0.5">
        {markers.map((marker) => (
          <li
            key={marker}
            className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-800 dark:text-amber-200 border border-amber-500/30"
          >
            {marker}
          </li>
        ))}
      </ul>
    </div>
  );
};
