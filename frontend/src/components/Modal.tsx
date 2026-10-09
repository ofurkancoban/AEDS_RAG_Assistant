import React, { useEffect } from 'react';
import { X } from 'lucide-react';

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: React.ReactNode;
  eyebrow?: React.ReactNode;
  icon?: React.ReactNode;
  /** Tailwind max-width class for the panel on sm+ screens. */
  maxWidth?: string;
  children: React.ReactNode;
}

/* A bottom sheet on phones, where a centred dialog leaves the action buttons
   out of thumb reach and a long body scrolls awkwardly between two margins;
   a centred dialog from sm up. */
export const Modal: React.FC<ModalProps> = ({
  isOpen,
  onClose,
  title,
  eyebrow,
  icon,
  maxWidth = 'sm:max-w-lg',
  children,
}) => {
  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-[70] flex items-end sm:items-center justify-center sm:p-6 bg-accent-950/45 backdrop-blur-[2px] animate-in"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      role="dialog"
      aria-modal="true"
    >
      <div
        className={`w-full ${maxWidth} max-h-[88dvh] flex flex-col bg-[var(--bg-elevated)] text-[var(--text)] border border-[var(--border)] shadow-[var(--shadow-lg)] rounded-t-2xl sm:rounded-2xl overflow-hidden animate-fade-up`}
      >
        <div className="h-1 w-full bg-gradient-to-r from-accent-700 via-accent-500 to-brass-400 shrink-0" />
        <div className="flex items-start justify-between gap-4 px-5 sm:px-6 pt-5 pb-4 border-b border-[var(--border)] shrink-0">
          <div className="flex items-start gap-3 min-w-0">
            {icon && (
              <div className="w-9 h-9 rounded-lg bg-accent-50 dark:bg-accent-900/60 text-accent-600 dark:text-accent-300 flex items-center justify-center shrink-0">
                {icon}
              </div>
            )}
            <div className="min-w-0">
              {eyebrow && <div className="eyebrow mb-1">{eyebrow}</div>}
              <h3 className="text-lg font-semibold leading-snug text-[var(--text)] break-words">{title}</h3>
            </div>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="-mr-1.5 p-1.5 rounded-lg text-[var(--text-muted)] hover:text-[var(--text)] hover:bg-[var(--bg-inset)] transition-colors cursor-pointer shrink-0"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="overflow-y-auto px-5 sm:px-6 py-5 pb-[max(1.25rem,env(safe-area-inset-bottom))]">
          {children}
        </div>
      </div>
    </div>
  );
};
