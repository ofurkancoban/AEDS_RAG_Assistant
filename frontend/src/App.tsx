import React, { Suspense, lazy, useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { ChatQueryResult, AdminStats } from './types';
import { Navbar, TabId } from './components/Navbar';
import { RagChatView } from './components/RagChatView';
import { LoginModal } from './components/LoginModal';
import { useAuth } from './context/AuthContext';
import { getStats } from './api/client';

// Every one of these is admin-only - a regular visitor (the common case:
// an anonymous student asking questions) never renders any of them, but
// previously still downloaded and parsed all six as part of the one main
// bundle before ever seeing the chat view. Split into their own chunks so
// that cost is paid only by someone who actually opens an admin tab.
const KnowledgeBaseView = lazy(() => import('./components/KnowledgeBaseView').then((m) => ({ default: m.KnowledgeBaseView })));
const RagSettingsView = lazy(() => import('./components/RagSettingsView').then((m) => ({ default: m.RagSettingsView })));
const VectorAnalyticsView = lazy(() => import('./components/VectorAnalyticsView').then((m) => ({ default: m.VectorAnalyticsView })));
const AdminApprovalView = lazy(() => import('./components/AdminApprovalView').then((m) => ({ default: m.AdminApprovalView })));
const UserManagementView = lazy(() => import('./components/UserManagementView').then((m) => ({ default: m.UserManagementView })));
const AnswerReviewView = lazy(() => import('./components/AnswerReviewView').then((m) => ({ default: m.AnswerReviewView })));

const AdminTabFallback: React.FC = () => (
  <div className="max-w-5xl mx-auto px-4 py-16 text-center text-[var(--text-muted)] text-sm flex items-center justify-center gap-2">
    <RefreshCw className="w-4 h-4 animate-spin" />
    <span>Loading...</span>
  </div>
);

export default function App() {
  const { isAdmin, identity, isReady } = useAuth();
  const [activeTab, setActiveTab] = useState<TabId>('chat');
  const [isLoginOpen, setIsLoginOpen] = useState(false);
  const [isNavOpen, setIsNavOpen] = useState(false);
  const [latestResult, setLatestResult] = useState<ChatQueryResult | null>(null);
  const [stats, setStats] = useState<AdminStats | null>(null);

  // The navbar's chunk/document/pending badges read from this. It used to be
  // fetched once per login, so approving a submission or ingesting a document
  // left the counts wrong until a full page reload; the admin views now call
  // refreshStats after any action that changes them.
  const refreshStats = useCallback(() => {
    if (!isAdmin) return;
    getStats().then(setStats).catch(() => setStats(null));
  }, [isAdmin]);

  useEffect(() => {
    if (!isAdmin) {
      setActiveTab('chat');
      setStats(null);
      return;
    }
    refreshStats();
  }, [isAdmin, refreshStats]);

  return (
    // App shell: exactly one viewport tall and never scrolls itself; anything
    // longer scrolls inside <main>, so the header stays put. h-dvh, not
    // h-screen: mobile Safari measures 100vh with its toolbar hidden, so
    // h-screen content ran under the toolbar instead of fitting above it.
    <div className="h-dvh bg-[var(--bg)] text-[var(--text)] font-sans flex flex-col relative overflow-hidden">
      <Navbar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        chunkCount={stats?.total_chunks ?? 0}
        docCount={stats?.total_sources ?? 0}
        pendingCount={stats?.pending_submissions ?? 0}
        pendingAnswers={stats?.pending_answers ?? 0}
        pendingSourceChanges={stats?.pending_source_changes ?? 0}
        onOpenLogin={() => setIsLoginOpen(true)}
        onOpenMenu={activeTab === 'chat' ? () => setIsNavOpen(true) : undefined}
      />

      {/* min-h-0 lets this shrink inside the flex column instead of being
          forced to its content height. The admin lists scroll here; the chat
          view fills it exactly and scrolls internally. */}
      {/* No z-index here on purpose: one would make <main> a stacking
          context and trap every modal rendered inside it beneath the header.
          Being later in the DOM is enough to paint over the fixed backdrop. */}
      <main className="flex-1 min-h-0 overflow-y-auto relative w-full">
        {/* Keyed on the identity so logging in or out starts a clean
            conversation. A thread belongs to exactly one identity and the
            server rejects a thread_id that is not the caller's, so carrying
            the old one across a sign-in would 403 on the next message. */}
        {activeTab === 'chat' && isReady && (
          <RagChatView
            key={identity?.id ?? 'anonymous'}
            onQueryResult={setLatestResult}
            isNavOpen={isNavOpen}
            onNavOpenChange={setIsNavOpen}
          />
        )}

        {isAdmin && activeTab !== 'chat' && (
          <Suspense fallback={<AdminTabFallback />}>
            {activeTab === 'knowledge' && <KnowledgeBaseView onCorpusChange={refreshStats} />}
            {activeTab === 'admin' && <AdminApprovalView onQueueChange={refreshStats} />}
            {activeTab === 'settings' && <RagSettingsView />}
            {activeTab === 'analytics' && <VectorAnalyticsView latestResult={latestResult} />}
            {activeTab === 'users' && <UserManagementView />}
            {activeTab === 'answers' && <AnswerReviewView onQueueChange={refreshStats} />}
          </Suspense>
        )}
      </main>

      <LoginModal isOpen={isLoginOpen} onClose={() => setIsLoginOpen(false)} />
    </div>
  );
}
