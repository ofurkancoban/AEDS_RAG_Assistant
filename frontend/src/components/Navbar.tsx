import React from 'react';
import {
  Database, MessageSquare, Settings, BarChart2, ShieldCheck,
  LogIn, LogOut, Users, MessagesSquare, Menu, GraduationCap,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { ThemeToggle } from './ThemeToggle';
import { BrandMark } from './BrandMark';
import { PROGRAMME } from '../config/programme';

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
  /** Opens the topic navigation as a drawer on screens too narrow to show
      it permanently. Absent outside the chat view. */
  onOpenMenu?: () => void;
}

/* Queue counts that mean "act on this" are amber; plain totals are blue. */
const CountBadge: React.FC<{ value: number; urgent?: boolean; title?: string }> = ({ value, urgent, title }) => (
  <span
    title={title}
    className={`min-w-[18px] h-[18px] px-1 inline-flex items-center justify-center rounded-full font-mono text-[10px] font-medium shrink-0 ${
      urgent
        ? 'bg-amber-400 text-amber-950'
        : 'bg-accent-100 text-accent-800 dark:bg-accent-500/20 dark:text-accent-200'
    }`}
  >
    {value}
  </span>
);

export const Navbar: React.FC<NavbarProps> = ({
  activeTab,
  setActiveTab,
  chunkCount,
  docCount,
  pendingCount = 0,
  pendingAnswers = 0,
  pendingSourceChanges = 0,
  onOpenLogin,
  onOpenMenu,
}) => {
  const { isAuthenticated, isAdmin, email, logout } = useAuth();

  const tabs: { id: TabId; label: string; icon: React.ElementType; badges?: React.ReactNode }[] = [
    { id: 'chat', label: 'Q&A Assistant', icon: MessageSquare },
    {
      id: 'knowledge',
      label: 'Knowledge Base',
      icon: Database,
      badges: (
        <>
          {docCount > 0 && <CountBadge value={docCount} title={`${docCount} documents`} />}
          {pendingSourceChanges > 0 && (
            <CountBadge value={pendingSourceChanges} urgent title={`${pendingSourceChanges} source page(s) changed since curation`} />
          )}
        </>
      ),
    },
    {
      id: 'admin',
      label: 'Admin Review',
      icon: ShieldCheck,
      badges: pendingCount > 0 ? <CountBadge value={pendingCount} urgent title={`${pendingCount} pending submissions`} /> : null,
    },
    {
      id: 'answers',
      label: 'Answer Review',
      icon: MessagesSquare,
      badges: pendingAnswers > 0 ? <CountBadge value={pendingAnswers} urgent title={`${pendingAnswers} answers awaiting review`} /> : null,
    },
    { id: 'analytics', label: 'Vector Analytics', icon: BarChart2 },
    { id: 'settings', label: 'RAG Config', icon: Settings },
    { id: 'users', label: 'Users', icon: Users },
  ];

  return (
    <header className="relative z-40 shrink-0 bg-[var(--bg-elevated)] border-b border-[var(--border)]">
      <div className="flex items-center h-14 pr-3 sm:pr-4">
        {onOpenMenu && (
          <button
            onClick={onOpenMenu}
            aria-label="Open topics"
            title="Topics"
            className="lg:hidden ml-2 flex items-center justify-center w-10 h-10 rounded-md text-[var(--text-secondary)] hover:bg-[var(--bg-inset)] cursor-pointer"
          >
            <Menu className="w-5 h-5" />
          </button>
        )}

        {/* Brand block: the same width as the topic navigation below it on
            desktop, so the two read as one column. */}
        <button
          onClick={() => setActiveTab('chat')}
          className="flex items-center gap-2.5 h-14 px-3 lg:px-4 lg:w-[272px] lg:border-r border-[var(--border)] shrink-0 text-left cursor-pointer"
        >
          <BrandMark size={30} />
          <span className="leading-tight min-w-0">
            <span className="flex items-center gap-2">
              <span className="text-[15px] font-semibold text-[var(--text)] whitespace-nowrap">Student Assistant</span>
              {isAdmin && (
                <span className="hidden sm:inline-flex items-center px-1.5 rounded border border-brass-500/40 bg-brass-50 dark:bg-brass-900/40 text-brass-700 dark:text-brass-300 text-[10px] font-semibold uppercase tracking-wider">
                  Admin
                </span>
              )}
            </span>
            <span className="hidden sm:block text-[11.5px] text-[var(--text-muted)] whitespace-nowrap">{PROGRAMME.university}</span>
          </span>
        </button>

        {/* The scope this assistant answers for. A label today; the place a
            programme selector goes once more than one programme is served. */}
        <div className="hidden md:flex items-center gap-2 ml-4 h-8 px-3 rounded-md border border-[var(--border)] bg-[var(--bg-subtle)] text-[13px] min-w-0">
          <GraduationCap className="w-4 h-4 text-accent-700 dark:text-accent-300 shrink-0" />
          <span className="text-[var(--text-muted)]">Programme</span>
          <span className="font-medium text-[var(--text)] truncate">
            {PROGRAMME.name} <span className="text-[var(--text-muted)] font-normal">({PROGRAMME.degree})</span>
          </span>
        </div>
        {chunkCount > 0 && (
          <span className="hidden xl:inline ml-3 font-mono text-[11px] text-emerald-700 dark:text-emerald-400">
            {chunkCount.toLocaleString()} passages indexed
          </span>
        )}

        <div className="flex-1" />

        <div className="flex items-center gap-1.5 shrink-0">
          <ThemeToggle />
          {isAuthenticated ? (
            <>
              <div className="hidden lg:flex flex-col text-right leading-tight px-2">
                <span className="text-[12.5px] font-medium text-[var(--text)] truncate max-w-[200px]">{email}</span>
                <span className="text-[10.5px] text-[var(--text-muted)] uppercase tracking-wider">{isAdmin ? 'Admin' : 'Staff'}</span>
              </div>
              <button
                onClick={logout}
                title="Log out"
                className="flex items-center gap-1.5 h-9 px-3 rounded-md border border-[var(--border)] text-[var(--text-secondary)] hover:bg-[var(--bg-subtle)] text-[13.5px] font-medium transition-colors cursor-pointer"
              >
                <LogOut className="w-4 h-4" />
                <span className="hidden sm:inline">Log out</span>
              </button>
            </>
          ) : (
            <button
              onClick={onOpenLogin}
              title="Staff sign-in"
              className="flex items-center gap-1.5 h-9 px-3 rounded-md bg-accent-800 hover:bg-accent-700 dark:bg-accent-600 dark:hover:bg-accent-500 text-white text-[13.5px] font-medium transition-colors cursor-pointer"
            >
              <LogIn className="w-4 h-4" />
              <span className="hidden sm:inline">Staff sign-in</span>
            </button>
          )}
        </div>
      </div>

      {/* Admin sections: an underlined tab row that scrolls sideways on a
          phone rather than wrapping into a block of buttons. */}
      {isAdmin && (
        <nav className="px-1 sm:px-3 overflow-x-auto no-scrollbar border-t border-[var(--border)]" aria-label="Admin sections">
          <div className="flex items-stretch gap-0.5 min-w-max">
            {tabs.map(({ id, label, icon: Icon, badges }) => {
              const active = activeTab === id;
              return (
                <button
                  key={id}
                  onClick={() => setActiveTab(id)}
                  aria-current={active ? 'page' : undefined}
                  className={`relative flex items-center gap-1.5 px-3 h-10 text-[13px] whitespace-nowrap transition-colors cursor-pointer ${
                    active ? 'text-[var(--text)] font-medium' : 'text-[var(--text-muted)] hover:text-[var(--text)]'
                  }`}
                >
                  <Icon className={`w-4 h-4 shrink-0 ${active ? 'text-accent-700 dark:text-accent-300' : ''}`} />
                  <span>{label}</span>
                  {badges}
                  <span
                    className={`absolute left-2 right-2 bottom-0 h-[2px] rounded-full ${active ? 'bg-accent-700 dark:bg-accent-400' : 'bg-transparent'}`}
                  />
                </button>
              );
            })}
          </div>
        </nav>
      )}
    </header>
  );
};
