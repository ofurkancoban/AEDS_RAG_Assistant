import React, { useEffect, useState } from 'react';
import {
  Users, UserPlus, RefreshCw, Trash2, ShieldCheck, ShieldOff,
  KeyRound, Mail, Lock, X, Info,
} from 'lucide-react';
import { StaffUser, createUser, deleteUser, listUsers, updateUser } from '../api/client';
import { useAuth } from '../context/AuthContext';

const MIN_PASSWORD_LENGTH = 8;

export const UserManagementView: React.FC = () => {
  const { identity } = useAuth();
  const [users, setUsers] = useState<StaffUser[]>([]);
  const [anonymousSessions, setAnonymousSessions] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [form, setForm] = useState({ email: '', password: '', role: 'user' as 'admin' | 'user' });
  const [formError, setFormError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = async () => {
    setIsLoading(true);
    try {
      const data = await listUsers();
      setUsers(data.users);
      setAnonymousSessions(data.anonymous_sessions);
    } catch (e) {
      console.error('Failed to load users:', e);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    setBusyId(-1);
    try {
      const created = await createUser(form);
      setForm({ email: '', password: '', role: 'user' });
      setIsFormOpen(false);
      setNotice(`Account created for ${created.email}. Share the password with them directly.`);
      await load();
    } catch (err: any) {
      setFormError(err.message || 'Could not create the account');
    } finally {
      setBusyId(null);
    }
  };

  const handleRoleChange = async (user: StaffUser) => {
    const nextRole = user.role === 'admin' ? 'user' : 'admin';
    setBusyId(user.id);
    try {
      await updateUser(user.id, { role: nextRole });
      await load();
    } catch (err: any) {
      alert(err.message || 'Could not change the role');
    } finally {
      setBusyId(null);
    }
  };

  const handleResetPassword = async (user: StaffUser) => {
    const password = prompt(`New password for ${user.email} (min. ${MIN_PASSWORD_LENGTH} characters):`);
    if (password === null) return;
    setBusyId(user.id);
    try {
      await updateUser(user.id, { password });
      setNotice(`Password updated for ${user.email}.`);
    } catch (err: any) {
      alert(err.message || 'Could not update the password');
    } finally {
      setBusyId(null);
    }
  };

  const handleDelete = async (user: StaffUser) => {
    if (!confirm(`Delete the account ${user.email}?\n\nAny submissions they reviewed stay on record, but stop showing their name.`)) return;
    setBusyId(user.id);
    try {
      await deleteUser(user.id);
      await load();
    } catch (err: any) {
      alert(err.message || 'Could not delete the account');
    } finally {
      setBusyId(null);
    }
  };

  const adminCount = users.filter((u) => u.role === 'admin').length;

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">

      <div className="glass rounded-3xl p-6 shadow-2xl space-y-4">
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center space-x-2.5">
              <div className="w-8 h-8 rounded-xl bg-accent-600/20 border border-accent-500/30 flex items-center justify-center text-accent-500 dark:text-accent-400">
                <Users className="w-5 h-5" />
              </div>
              <h1 className="text-lg font-extrabold text-[var(--text)] tracking-tight">Staff Accounts</h1>
            </div>
            <p className="text-xs text-[var(--text-secondary)]">
              Accounts exist only for managing the assistant. Students never need one.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2.5 w-full md:w-auto shrink-0">
            <button
              onClick={load}
              className="flex-1 md:flex-none flex items-center justify-center space-x-2 glass-well hover:bg-[var(--bg-inset)]/70 text-[var(--text-secondary)] text-xs font-bold px-4 py-2.5 rounded-2xl transition-all cursor-pointer shadow-md"
            >
              <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
              <span>Refresh</span>
            </button>
            <button
              onClick={() => { setIsFormOpen((open) => !open); setFormError(null); }}
              className="flex-1 md:flex-none flex items-center justify-center space-x-2 bg-gradient-to-r from-accent-600 to-accent-700 hover:from-accent-500 hover:to-accent-600 text-white text-xs font-bold px-4.5 py-2.5 rounded-2xl shadow-lg shadow-accent-600/30 border border-accent-400/30 transition-all cursor-pointer"
            >
              <UserPlus className="w-4 h-4" />
              <span>Add User</span>
            </button>
          </div>
        </div>

        {/* States plainly that the visitor count is not a list of people - the
            assistant is used anonymously and there is nothing to show. */}
        <div className="flex items-start gap-2.5 text-[11px] text-[var(--text-muted)] glass-well rounded-2xl p-3">
          <Info className="w-3.5 h-3.5 text-accent-500 dark:text-accent-400 shrink-0 mt-0.5" />
          <span>
            <strong className="text-[var(--text-secondary)]">{anonymousSessions}</strong> anonymous
            session{anonymousSessions === 1 ? '' : 's'} have used the assistant. They hold no personal
            details and cannot sign in, so they are counted rather than listed.
          </span>
        </div>
      </div>

      {notice && (
        <div className="rounded-2xl px-4 py-3 border border-emerald-500/25 bg-emerald-500/10 text-xs text-emerald-700 dark:text-emerald-300 flex items-center justify-between gap-3">
          <span>{notice}</span>
          <button onClick={() => setNotice(null)} className="cursor-pointer shrink-0"><X className="w-3.5 h-3.5" /></button>
        </div>
      )}

      {isFormOpen && (
        <form onSubmit={handleCreate} className="glass rounded-3xl p-6 space-y-4 shadow-2xl">
          <div className="flex items-center space-x-2 border-b border-accent-500/10 pb-3.5">
            <UserPlus className="w-5 h-5 text-accent-500 dark:text-accent-400" />
            <h2 className="text-sm font-extrabold text-[var(--text)]">New staff account</h2>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
            <div className="space-y-1 sm:col-span-1">
              <label className="font-bold text-[var(--text-secondary)]">Email</label>
              <div className="flex items-center glass-well rounded-xl px-3 focus-within:border-accent-500">
                <Mail className="w-3.5 h-3.5 text-[var(--text-muted)] shrink-0" />
                <input
                  type="email"
                  required
                  value={form.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                  placeholder="colleague@uol.de"
                  className="w-full bg-transparent p-2.5 text-[var(--text)] focus:outline-none"
                />
              </div>
            </div>

            <div className="space-y-1 sm:col-span-1">
              <label className="font-bold text-[var(--text-secondary)]">
                Password <span className="font-normal text-[var(--text-muted)]">(min. {MIN_PASSWORD_LENGTH})</span>
              </label>
              <div className="flex items-center glass-well rounded-xl px-3 focus-within:border-accent-500">
                <Lock className="w-3.5 h-3.5 text-[var(--text-muted)] shrink-0" />
                <input
                  type="text"
                  required
                  minLength={MIN_PASSWORD_LENGTH}
                  value={form.password}
                  onChange={(e) => setForm({ ...form, password: e.target.value })}
                  placeholder="set an initial password"
                  className="w-full bg-transparent p-2.5 text-[var(--text)] focus:outline-none font-mono"
                />
              </div>
            </div>

            <div className="space-y-1 sm:col-span-1">
              <label className="font-bold text-[var(--text-secondary)]">Role</label>
              <select
                value={form.role}
                onChange={(e) => setForm({ ...form, role: e.target.value as 'admin' | 'user' })}
                className="w-full glass-well rounded-xl p-2.5 text-[var(--text)] focus:outline-none focus:border-accent-500 cursor-pointer"
              >
                <option value="user">user - can sign in, no admin screens</option>
                <option value="admin">admin - full access</option>
              </select>
            </div>
          </div>

          {formError && (
            <p className="text-[11px] text-rose-600 dark:text-rose-400 bg-rose-500/10 border border-rose-500/20 rounded-xl px-3 py-2">
              {formError}
            </p>
          )}

          {/* Shown in the clear on purpose: there is no email delivery here, so
              the admin has to be able to read the password to pass it on. */}
          <p className="text-[11px] text-[var(--text-muted)]">
            The password is visible so you can share it with the person directly. They can be given a
            new one at any time from the list below.
          </p>

          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setIsFormOpen(false)}
              className="px-4 py-2.5 glass-well hover:bg-[var(--bg-inset)]/70 text-[var(--text-secondary)] rounded-2xl text-xs font-bold cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={busyId === -1}
              className="flex items-center space-x-2 bg-gradient-to-r from-accent-600 to-accent-700 hover:from-accent-500 hover:to-accent-600 text-white text-xs font-bold px-5 py-2.5 rounded-2xl shadow-lg shadow-accent-600/30 border border-accent-400/30 transition-all cursor-pointer disabled:opacity-50"
            >
              <UserPlus className="w-4 h-4" />
              <span>{busyId === -1 ? 'Creating...' : 'Create account'}</span>
            </button>
          </div>
        </form>
      )}

      <div className="glass rounded-3xl p-4 space-y-3 shadow-2xl">
        <div className="text-xs font-extrabold text-accent-500 dark:text-accent-400 uppercase tracking-wider px-1">
          Accounts ({users.length})
        </div>

        {users.length === 0 ? (
          <div className="py-12 text-center text-[var(--text-faint)] text-xs">
            {isLoading ? 'Loading...' : 'No staff accounts.'}
          </div>
        ) : (
          <div className="space-y-2">
            {users.map((user) => {
              const isSelf = user.id === identity?.id;
              const isLastAdmin = user.role === 'admin' && adminCount <= 1;
              const busy = busyId === user.id;
              return (
                <div key={user.id} className="p-3.5 rounded-2xl glass-well flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-xs font-bold text-[var(--text)] truncate">{user.email}</span>
                      {/* Brass, matching the navbar's own Admin Mode badge:
                          both say "this account has staff powers", and having
                          them in two different yellows made them look like two
                          unrelated states. */}
                      <span className={`text-[9px] font-extrabold uppercase tracking-wide px-1.5 py-0.5 rounded-full border ${
                        user.role === 'admin'
                          ? 'bg-brass-500/15 text-brass-700 dark:text-brass-300 border-brass-500/35'
                          : 'bg-slate-500/15 text-slate-600 dark:text-slate-300 border-slate-500/30'
                      }`}>
                        {user.role}
                      </span>
                      {isSelf && (
                        <span className="text-[9px] font-extrabold uppercase tracking-wide px-1.5 py-0.5 rounded-full bg-accent-500/15 text-accent-600 dark:text-accent-300 border border-accent-500/30">
                          you
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2 text-[10px] text-[var(--text-muted)] mt-0.5">
                      <span>added {new Date(user.created_at).toLocaleDateString('en-US')}</span>
                      {user.reviews > 0 && <><span>•</span><span>{user.reviews} review{user.reviews === 1 ? '' : 's'}</span></>}
                      {user.submissions > 0 && <><span>•</span><span>{user.submissions} submission{user.submissions === 1 ? '' : 's'}</span></>}
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center gap-1.5 shrink-0">
                    <button
                      onClick={() => handleResetPassword(user)}
                      disabled={busy}
                      title="Set a new password"
                      className="flex items-center gap-1.5 px-3 py-1.5 glass-well hover:bg-[var(--bg-inset)] text-[var(--text-secondary)] rounded-xl text-[11px] font-bold cursor-pointer disabled:opacity-50"
                    >
                      <KeyRound className="w-3.5 h-3.5" />
                      <span>Password</span>
                    </button>

                    <button
                      onClick={() => handleRoleChange(user)}
                      // Both cases would leave nobody able to reach the admin
                      // screens; the server refuses them too.
                      disabled={busy || (user.role === 'admin' && (isSelf || isLastAdmin))}
                      title={
                        user.role === 'admin'
                          ? isSelf
                            ? 'You cannot remove your own admin access'
                            : isLastAdmin
                            ? 'This is the last admin'
                            : 'Make this a plain user'
                          : 'Grant admin access'
                      }
                      className="flex items-center gap-1.5 px-3 py-1.5 bg-accent-500/15 hover:bg-accent-500/25 text-accent-600 dark:text-accent-300 border border-accent-500/30 rounded-xl text-[11px] font-bold cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      {user.role === 'admin' ? <ShieldOff className="w-3.5 h-3.5" /> : <ShieldCheck className="w-3.5 h-3.5" />}
                      <span>{user.role === 'admin' ? 'Demote' : 'Make admin'}</span>
                    </button>

                    <button
                      onClick={() => handleDelete(user)}
                      disabled={busy || isSelf || isLastAdmin}
                      title={isSelf ? 'You cannot delete your own account' : isLastAdmin ? 'This is the last admin' : 'Delete this account'}
                      className="p-1.5 text-[var(--text-faint)] hover:text-rose-500 hover:bg-[var(--bg-inset)] rounded-xl transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:text-[var(--text-faint)]"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

    </div>
  );
};
