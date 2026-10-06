import React, { useEffect, useState } from 'react';
import { Sparkles } from 'lucide-react';
import { VersionInfo } from '../types';
import { getVersion } from '../api/client';
import { Modal } from './Modal';
import { useI18n } from '../i18n';

/* Inline "v1.2.3 - What's new" link that opens the changelog. Lives in the
   sidebar footer rather than pinned to a viewport corner, where on a phone
   it sat on top of the conversation. */
export const VersionBadge: React.FC = () => {
  const [info, setInfo] = useState<VersionInfo | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const { t } = useI18n();

  useEffect(() => {
    getVersion().then(setInfo).catch(() => setInfo(null));
  }, []);

  // Better nothing than a link reading "vundefined".
  if (!info) return null;

  return (
    <>
      <button
        onClick={() => setIsOpen(true)}
        className="inline-flex items-center gap-1.5 font-mono text-[11px] text-[var(--text-muted)] hover:text-accent-600 dark:hover:text-accent-300 transition-colors cursor-pointer"
        title={t.whatsNew}
      >
        <span>v{info.version}</span>
        <span className="text-[var(--text-faint)]">·</span>
        <span className="underline decoration-dotted underline-offset-2">{t.whatsNew}</span>
      </button>

      <Modal
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        eyebrow="Changelog"
        title={t.whatsNew}
        icon={<Sparkles className="w-4 h-4" />}
      >
        <ol className="space-y-6">
          {info.changelog.map((entry) => (
            <li key={entry.version} className="relative pl-5 border-l border-[var(--border)]">
              <span className="absolute -left-[5px] top-1.5 w-[9px] h-[9px] rounded-full bg-brass-400 ring-4 ring-[var(--bg-elevated)]" />
              <div className="flex items-baseline gap-2 mb-2">
                <span className="font-mono text-sm font-medium text-accent-700 dark:text-accent-300">v{entry.version}</span>
                <span className="text-[11px] text-[var(--text-faint)] font-mono">{entry.date}</span>
              </div>
              {Object.entries(entry.sections).map(([section, items]) => (
                <div key={section} className="mb-2 last:mb-0">
                  <span className="eyebrow">{section}</span>
                  <ul className="mt-1 space-y-1.5">
                    {items.map((item, idx) => (
                      <li key={idx} className="text-[13px] text-[var(--text-secondary)] leading-relaxed">
                        {item}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </li>
          ))}
        </ol>
      </Modal>
    </>
  );
};
