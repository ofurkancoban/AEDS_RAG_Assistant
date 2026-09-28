import React, { useEffect, useState } from 'react';
import { X, Tag, Sparkles } from 'lucide-react';
import { VersionInfo } from '../types';
import { getVersion } from '../api/client';

export const VersionBadge: React.FC = () => {
  const [info, setInfo] = useState<VersionInfo | null>(null);
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    getVersion().then(setInfo).catch(() => setInfo(null));
  }, []);

  // Nothing to show and nothing to open if the fetch failed or hasn't
  // resolved yet - better than a corner tag that reads "vundefined".
  if (!info) return null;

  return (
    <>
      <button
        onClick={() => setIsOpen(true)}
        className="fixed bottom-3 right-3 z-40 flex items-center gap-1 px-2.5 py-1 rounded-full glass-well text-[10px] font-mono font-bold text-[var(--text-muted)] hover:text-accent-600 dark:hover:text-accent-300 border border-[var(--border)] shadow-sm transition-colors cursor-pointer"
        title="What's new"
      >
        <Tag className="w-3 h-3" />
        <span>v{info.version}</span>
      </button>

      {isOpen && (
        <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="glass-strong rounded-2xl max-w-lg w-full max-h-[80vh] flex flex-col text-[var(--text)]">
            <div className="flex items-center justify-between border-b border-[var(--border)] p-5 pb-4 shrink-0">
              <div className="flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-accent-500" />
                <h3 className="text-base font-bold">What's new</h3>
              </div>
              <button onClick={() => setIsOpen(false)} className="p-1 text-[var(--text-muted)] hover:text-[var(--text)] cursor-pointer">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="overflow-y-auto p-5 pt-4 space-y-5">
              {info.changelog.map((entry) => (
                <div key={entry.version} className="space-y-2">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono font-black text-accent-600 dark:text-accent-300">v{entry.version}</span>
                    <span className="text-[10px] text-[var(--text-faint)]">{entry.date}</span>
                  </div>
                  {Object.entries(entry.sections).map(([section, items]) => (
                    <div key={section} className="pl-1">
                      <span className="text-[10px] font-bold uppercase tracking-wider text-[var(--text-muted)]">{section}</span>
                      <ul className="mt-1 space-y-1">
                        {items.map((item, idx) => (
                          <li key={idx} className="text-xs text-[var(--text-secondary)] leading-relaxed flex gap-2">
                            <span className="text-accent-500 shrink-0">-</span>
                            <span>{item}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  );
};
