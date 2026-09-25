import React from 'react';
import { Database, MessageSquare, Settings, BarChart2, ShieldCheck, Sigma, Activity, LogIn, LogOut, Users, MessagesSquare } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { ThemeToggle } from './ThemeToggle';

export type TabId = 'chat' | 'knowledge' | 'settings' | 'analytics' | 'admin' | 'users' | 'answers';

interface NavbarProps {
  activeTab: TabId;
  setActiveTab: (tab: TabId) => void;
  chunkCount: number;
  docCount: number;
  pendingCount?: number;
  pendingAnswers?: number;
  pendingSourceChanges?: number;
  onOpenLogin: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  activeTab,
  setActiveTab,
  chunkCount,
  docCount,
  pendingCount = 0,
  pendingAnswers = 0,
  pendingSourceChanges = 0,
  onOpenLogin,
}) => {
  const { isAuthenticated, isAdmin, email, logout } = useAuth();

  const tabButtonClass = (tab: TabId) =>
    `flex items-center space-x-1.5 px-2.5 sm:px-3.5 py-2 rounded-xl text-[11px] sm:text-xs font-bold transition-all cursor-pointer whitespace-nowrap ${
      activeTab === tab
        ? 'bg-gradient-to-r from-accent-600 to-accent-700 text-white shadow-lg shadow-accent-600/30 border border-accent-400/30'
        : 'text-[var(--text-muted)] hover:text-[var(--text)] hover:bg-[var(--bg-inset)]/50'
    }`;

  return (
    <header className="glass-strong border-x-0 border-t-0 text-[var(--text)] shrink-0 z-40">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16 gap-3">

          {/* Brand Logo & Name */}
          <div className="flex items-center space-x-3 shrink-0 min-w-0">
            <div className="relative group cursor-pointer shrink-0" onClick={() => setActiveTab('chat')}>
              <div className="absolute -inset-0.5 bg-gradient-to-r from-accent-600 to-brass-400 rounded-xl blur opacity-40 group-hover:opacity-75 transition duration-300"></div>
              <div className="relative w-9 h-9 sm:w-10 sm:h-10 rounded-xl bg-[var(--bg-elevated)] flex items-center justify-center text-[var(--text)] border border-accent-500/30">
                {/* Sigma, not a processor chip. The mark stands for the
                    programme rather than the machinery: Applied Economics
                    and Data Science is a statistics degree, and the same
                    notation already drifts across the background (see
                    FloatingBackground). A letterform also survives the
                    16px it renders at on a phone, where the chart glyphs
                    turn to mush. */}
                <Sigma className="w-4 h-4 sm:w-5 sm:h-5 text-accent-400" />
              </div>
            </div>
            <div className="min-w-0">
              <div className="flex items-center space-x-2 whitespace-nowrap">
                <span className="font-extrabold text-sm sm:text-base tracking-tight bg-gradient-to-r from-[var(--text)] via-[var(--text-secondary)] to-accent-500 bg-clip-text text-transparent truncate">
                  AEDS RAG Assistant
                </span>
                {/* Brass rather than amber: this marks who you are, not that
                    something needs attention. Amber is kept for the queue
                    counts below, which do mean "act on this" - two badges in
                    the same yellow made them read as one thing. */}
                {isAdmin && (
                  <span className="hidden sm:inline text-[9px] sm:text-[10px] font-extrabold px-2 py-0.5 rounded-full border tracking-wide uppercase shrink-0 bg-brass-500/12 text-brass-700 dark:text-brass-300 border-brass-500/35 shadow-sm shadow-brass-500/10">
                    Admin Mode
                  </span>
                )}
              </div>
              <p className="text-[11px] text-[var(--text-muted)] hidden xl:flex items-center space-x-2 font-medium whitespace-nowrap">
                <span>Applied Economics &amp; Data Science</span>
                {/* Only shown once a real count is known. The stats call is
                    admin-only, so for a visitor this read "0 chunks indexed"
                    against a corpus of several hundred. */}
                {chunkCount > 0 && (
                  <>
                    <span className="text-[var(--text-faint)]">•</span>
                    <span className="text-emerald-600 dark:text-emerald-400 font-mono text-[10px] flex items-center gap-1">
                      <Activity className="w-3 h-3 animate-pulse" />
                      {chunkCount} chunks indexed
                    </span>
                  </>
                )}
              </p>
            </div>
          </div>

          {/* A centred pill reading "Student & Faculty Academic Search
              Portal" used to sit here. It restated the brand two words to its
              left and could not be clicked, so it was chrome describing
              chrome. */}

          {/* Account Area */}
          <div className="flex items-center space-x-2 shrink-0">
            <ThemeToggle />
            {isAuthenticated ? (
              <div className="flex items-center space-x-2">
                <div className="hidden lg:flex flex-col text-right leading-tight">
                  <span className="text-xs font-bold text-[var(--text)] truncate max-w-[140px]">{email}</span>
                  <span className="text-[9px] text-[var(--text-muted)] font-mono uppercase">{isAdmin ? 'admin' : 'user'}</span>
                </div>
                <button
                  onClick={logout}
                  className="flex items-center space-x-1.5 glass-well hover:bg-[var(--bg-inset)] text-[var(--text-secondary)] text-xs font-semibold px-3 py-2 rounded-2xl transition-all cursor-pointer whitespace-nowrap shrink-0"
                >
                  <LogOut className="w-3.5 h-3.5 shrink-0" />
                  <span className="hidden sm:inline">Log out</span>
                </button>
              </div>
            ) : (
              <button
                onClick={onOpenLogin}
                className="flex items-center space-x-1.5 bg-gradient-to-r from-accent-600 to-accent-700 hover:from-accent-500 hover:to-accent-600 text-white text-xs font-bold px-3 py-2 sm:px-3.5 sm:py-2 rounded-2xl shadow-lg shadow-accent-600/30 transition-all border border-accent-400/30 cursor-pointer whitespace-nowrap shrink-0"
              >
                <LogIn className="w-3.5 h-3.5 shrink-0" />
                {/* Registered accounts are no longer admin-only, so this is a
                    general sign-in, not an admin door. */}
                <span className="hidden sm:inline">Log in</span>
              </button>
            )}
          </div>
        </div>

        {/* Admin Nav - own full-width row so it never has to compete with the
            brand/account areas for space and can wrap instead of overflowing. */}
        {isAdmin && (
          <nav className="flex flex-wrap items-center gap-1.5 p-1.5 mb-3 glass-well rounded-2xl">
            <button onClick={() => setActiveTab('chat')} className={tabButtonClass('chat')}>
              <MessageSquare className="w-3.5 h-3.5 shrink-0" />
              <span>Q&amp;A Assistant</span>
            </button>

            <button onClick={() => setActiveTab('knowledge')} className={tabButtonClass('knowledge')}>
              <Database className="w-3.5 h-3.5 shrink-0" />
              <span>Knowledge Base</span>
              {docCount > 0 && (
                <span className="bg-accent-500/20 text-accent-600 dark:text-accent-300 text-[10px] px-1.5 py-0.5 rounded-full border border-accent-500/30 font-mono font-bold shrink-0">
                  {docCount}
                </span>
              )}
              {pendingSourceChanges > 0 && (
                <span
                  className="bg-amber-400 text-slate-950 font-black text-[10px] px-1.5 py-0.5 rounded-full font-mono shadow-md animate-pulse shrink-0"
                  title={`${pendingSourceChanges} source page(s) changed since curation`}
                >
                  {pendingSourceChanges}
                </span>
              )}
            </button>

            <button onClick={() => setActiveTab('admin')} className={tabButtonClass('admin')}>
              <ShieldCheck className="w-3.5 h-3.5 text-amber-500 dark:text-amber-300 shrink-0" />
              <span>Admin Review</span>
              {pendingCount > 0 && (
                <span className="bg-amber-400 text-slate-950 font-black text-[10px] px-1.5 py-0.5 rounded-full font-mono shadow-md animate-pulse shrink-0">
                  {pendingCount}
                </span>
              )}
            </button>

            <button onClick={() => setActiveTab('answers')} className={tabButtonClass('answers')}>
              <MessagesSquare className="w-3.5 h-3.5 shrink-0" />
              <span>Answer Review</span>
              {pendingAnswers > 0 && (
                <span className="bg-amber-400 text-slate-950 font-black text-[10px] px-1.5 py-0.5 rounded-full font-mono shadow-md shrink-0">
                  {pendingAnswers}
                </span>
              )}
            </button>

            <button onClick={() => setActiveTab('analytics')} className={tabButtonClass('analytics')}>
              <BarChart2 className="w-3.5 h-3.5 shrink-0" />
              <span>Vector Analytics</span>
            </button>

            <button onClick={() => setActiveTab('settings')} className={tabButtonClass('settings')}>
              <Settings className="w-3.5 h-3.5 shrink-0" />
              <span>RAG Config</span>
            </button>

            <button onClick={() => setActiveTab('users')} className={tabButtonClass('users')}>
              <Users className="w-3.5 h-3.5 shrink-0" />
              <span>Users</span>
            </button>
          </nav>
        )}

      </div>
    </header>
  );
};
