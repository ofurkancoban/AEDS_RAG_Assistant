import React, { useCallback, useEffect, useState } from 'react';
import { ChatQueryResult, AdminStats } from './types';
import { Navbar, TabId } from './components/Navbar';
import { KnowledgeBaseView } from './components/KnowledgeBaseView';
import { RagChatView } from './components/RagChatView';
import { RagSettingsView } from './components/RagSettingsView';
import { VectorAnalyticsView } from './components/VectorAnalyticsView';
import { AdminApprovalView } from './components/AdminApprovalView';
import { UserManagementView } from './components/UserManagementView';
import { AnswerReviewView } from './components/AnswerReviewView';
import { LoginModal } from './components/LoginModal';
import { FloatingBackground } from './components/FloatingBackground';
import { VersionBadge } from './components/VersionBadge';
import { VisitorCounter } from './components/VisitorCounter';
import { useAuth } from './context/AuthContext';
import { getStats } from './api/client';

export default function App() {
  const { isAdmin, identity, isReady } = useAuth();
  const [activeTab, setActiveTab] = useState<TabId>('chat');
  const [isLoginOpen, setIsLoginOpen] = useState(false);
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
    // App shell: the page itself is exactly one viewport tall and never
    // scrolls. Anything longer than the space available scrolls inside <main>
    // instead, so the navbar stays put and the chat view can size itself to
    // whatever is left rather than guessing.
    <div className="h-screen bg-[var(--bg)] text-[var(--text)] font-sans selection:bg-accent-500 selection:text-white flex flex-col relative overflow-hidden">

      {/* Blurred color fields - the "light source" every glass panel in the
          app blurs and refracts. Glassmorphism reads as glass only when
          there's something colorful behind it to distort.

          Oxford navy is a far darker, less saturated hue than the indigo
          these used to be, so the old opacities turned the light theme grey
          rather than blue. Light mode therefore leans on the mid steps at
          higher opacity, while dark mode keeps them low - the same tint that
          barely registers on white is more than enough against near-black.
          The brass field is the one warm note; it stops the page reading as
          a single flat wash of navy. */}
      <div className="fixed top-[-10%] left-[-5%] w-[560px] h-[560px] bg-accent-500/35 dark:bg-accent-600/25 rounded-full blur-[130px] pointer-events-none z-0"></div>
      <div className="fixed bottom-[-10%] right-[-5%] w-[640px] h-[640px] bg-accent-600/30 dark:bg-accent-700/30 rounded-full blur-[160px] pointer-events-none z-0"></div>
      <div className="fixed top-[40%] right-[15%] w-[380px] h-[380px] bg-accent-400/25 dark:bg-accent-500/15 rounded-full blur-[120px] pointer-events-none z-0"></div>
      <div className="fixed top-[65%] left-[10%] w-[320px] h-[320px] bg-brass-400/14 dark:bg-brass-500/14 rounded-full blur-[130px] pointer-events-none z-0"></div>
      <FloatingBackground />

      <Navbar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        chunkCount={stats?.total_chunks ?? 0}
        docCount={stats?.total_sources ?? 0}
        pendingCount={stats?.pending_submissions ?? 0}
        pendingAnswers={stats?.pending_answers ?? 0}
        pendingSourceChanges={stats?.pending_source_changes ?? 0}
        onOpenLogin={() => setIsLoginOpen(true)}
      />

      {/* min-h-0 is what lets this shrink inside the flex column instead of
          being forced to its content height, which is what would push the page
          past one viewport. Views longer than the space available (the admin
          lists) scroll here; the chat view fills it exactly and does not. */}
      <main className="flex-1 min-h-0 overflow-y-auto z-10 relative w-full">
        {/* Keyed on the identity so logging in or out starts a clean
            conversation. A thread belongs to exactly one identity and the
            server rejects a thread_id that is not the caller's, so carrying
            the old one across a sign-in would 403 on the next message. */}
        {activeTab === 'chat' && isReady && (
          <RagChatView
            key={identity?.id ?? 'anonymous'}
            onOpenAdminMode={isAdmin ? () => setActiveTab('admin') : undefined}
            onQueryResult={setLatestResult}
          />
        )}

        {isAdmin && activeTab === 'knowledge' && <KnowledgeBaseView onCorpusChange={refreshStats} />}
        {isAdmin && activeTab === 'admin' && <AdminApprovalView onQueueChange={refreshStats} />}
        {isAdmin && activeTab === 'settings' && <RagSettingsView />}
        {isAdmin && activeTab === 'analytics' && <VectorAnalyticsView latestResult={latestResult} />}
        {isAdmin && activeTab === 'users' && <UserManagementView />}
        {isAdmin && activeTab === 'answers' && <AnswerReviewView onQueueChange={refreshStats} />}
      </main>

      <LoginModal isOpen={isLoginOpen} onClose={() => setIsLoginOpen(false)} />
      <VersionBadge />
      <VisitorCounter />

    </div>
  );
}
