import React, { useState } from 'react';
import { ShieldCheck, Mail, Lock, X } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

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

  if (!isOpen) return null;

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

  return (
    <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-md flex items-center justify-center p-4">
      <div className="glass-strong rounded-3xl max-w-sm w-full text-[var(--text)] shadow-2xl p-6 space-y-4 animate-in fade-in zoom-in duration-200">
        <div className="flex items-center justify-between border-b border-[var(--border)] pb-3">
          <div className="flex items-center space-x-2">
            <div className="p-2 bg-accent-500/20 text-accent-500 dark:text-accent-400 rounded-xl border border-accent-400/30">
              <ShieldCheck className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-[var(--text)]">Staff sign-in</h3>
              <p className="text-[11px] text-[var(--text-muted)]">
                For managing documents and reviewing submissions. Asking questions
                needs no account - the assistant is used anonymously.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-[var(--text-muted)] hover:text-[var(--text)] p-1 rounded-lg hover:bg-[var(--bg-inset)] transition-colors cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-3 text-xs">
          <div className="space-y-1">
            <label className="font-semibold text-[var(--text-secondary)]">Email</label>
            <div className="flex items-center glass-well rounded-xl px-3 focus-within:border-accent-500">
              <Mail className="w-3.5 h-3.5 text-[var(--text-muted)] shrink-0" />
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@university.edu"
                required
                className="w-full bg-transparent p-2.5 text-[var(--text)] focus:outline-none"
              />
            </div>
          </div>

          <div className="space-y-1">
            <label className="font-semibold text-[var(--text-secondary)]">Password</label>
            <div className="flex items-center glass-well rounded-xl px-3 focus-within:border-accent-500">
              <Lock className="w-3.5 h-3.5 text-[var(--text-muted)] shrink-0" />
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                required
                className="w-full bg-transparent p-2.5 text-[var(--text)] focus:outline-none"
              />
            </div>
          </div>

          {error && (
            <p className="text-rose-600 dark:text-rose-400 bg-rose-500/10 border border-rose-500/20 rounded-xl px-3 py-2">{error}</p>
          )}

          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full bg-accent-600 hover:bg-accent-500 disabled:opacity-50 text-white font-bold rounded-xl py-2.5 shadow-lg shadow-accent-600/25 transition-all cursor-pointer"
          >
            {isSubmitting ? 'Signing in...' : 'Log in'}
          </button>

          <p className="text-center text-[10px] text-[var(--text-muted)] pt-1">
            Accounts are created by the programme team, not through this form.
          </p>
        </form>
      </div>
    </div>
  );
};
