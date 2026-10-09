import React, { useState } from 'react';
import { KeyRound, Mail, Lock, Loader2 } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { Modal } from './Modal';

interface LoginModalProps {
  isOpen: boolean;
  onClose: () => void;
}

// Sign-in is for staff only. Everyone using the assistant stays anonymous -
// there is deliberately no way to create an account here, and the backend
// refuses registration once an admin exists (see api/routes_auth.py).
export const LoginModal: React.FC<LoginModalProps> = ({ isOpen, onClose }) => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const { login } = useAuth();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await login(email, password);
      setEmail('');
      setPassword('');
      onClose();
    } catch (err: any) {
      setError(err.message || 'Something went wrong');
    } finally {
      setIsSubmitting(false);
    }
  }

  const fieldClass =
    'flex items-center gap-2.5 h-11 px-3 rounded-lg bg-[var(--bg-subtle)] border border-[var(--border)] focus-within:border-accent-500 focus-within:ring-3 focus-within:ring-accent-500/15 transition-all';

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      eyebrow="Programme staff"
      title="Staff sign-in"
      icon={<KeyRound className="w-4 h-4" />}
      maxWidth="sm:max-w-md"
    >
      <p className="text-[13.5px] text-[var(--text-secondary)] leading-relaxed mb-5">
        For managing documents and reviewing submissions. Asking questions needs no
        account - the assistant is used anonymously.
      </p>

      <form onSubmit={handleSubmit} className="space-y-4">
        <label className="block space-y-1.5">
          <span className="text-[13px] font-medium text-[var(--text-secondary)]">Email</span>
          <div className={fieldClass}>
            <Mail className="w-4 h-4 text-[var(--text-faint)] shrink-0" />
            <input
              type="email"
              autoComplete="username"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@uol.de"
              required
              className="w-full bg-transparent text-base sm:text-[14px] text-[var(--text)] placeholder:text-[var(--text-faint)] focus:outline-none"
            />
          </div>
        </label>

        <label className="block space-y-1.5">
          <span className="text-[13px] font-medium text-[var(--text-secondary)]">Password</span>
          <div className={fieldClass}>
            <Lock className="w-4 h-4 text-[var(--text-faint)] shrink-0" />
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              required
              className="w-full bg-transparent text-base sm:text-[14px] text-[var(--text)] placeholder:text-[var(--text-faint)] focus:outline-none"
            />
          </div>
        </label>

        {error && (
          <p className="text-[13px] text-rose-700 dark:text-rose-300 bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900 rounded-lg px-3 py-2">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={isSubmitting}
          className="w-full h-11 flex items-center justify-center gap-2 rounded-lg bg-accent-700 hover:bg-accent-600 dark:bg-accent-600 dark:hover:bg-accent-500 disabled:opacity-60 text-white text-[14px] font-medium shadow-sm transition-colors cursor-pointer"
        >
          {isSubmitting && <Loader2 className="w-4 h-4 animate-spin" />}
          {isSubmitting ? 'Signing in...' : 'Sign in'}
        </button>

        <p className="text-center text-[12px] text-[var(--text-muted)]">
          Accounts are created by the programme team, not through this form.
        </p>
      </form>
    </Modal>
  );
};
