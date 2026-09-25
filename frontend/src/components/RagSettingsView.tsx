import React, { useEffect, useState } from 'react';
import { Sliders, Layers, Sparkles, RotateCcw, Lock, Save, RefreshCw, Eye, Copy } from 'lucide-react';
import { AdminConfig } from '../types';
import { getConfig, putConfig } from '../api/client';
import { ALLOWED_GEMINI_MODELS, ALLOWED_LLM_PROVIDERS } from '../api/constants';

export const RagSettingsView: React.FC = () => {
  const [config, setConfig] = useState<AdminConfig | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [systemPrompt, setSystemPrompt] = useState('');
  // A free-text field (no fixed allowlist, unlike gemini_model's dropdown),
  // so it needs its own draft state and saves on blur rather than on every
  // keystroke.
  const [openrouterModelDraft, setOpenrouterModelDraft] = useState('');

  const load = async () => {
    setIsLoading(true);
    try {
      const data = await getConfig();
      setConfig(data);
      setSystemPrompt(data.system_prompt_override.value || '');
      setOpenrouterModelDraft(data.openrouter_model.value || '');
    } catch (e) {
      console.error('Failed to load config:', e);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const save = async (fields: Parameters<typeof putConfig>[0]) => {
    setIsSaving(true);
    try {
      const updated = await putConfig(fields);
      setConfig(updated);
      setSystemPrompt(updated.system_prompt_override.value || '');
      setOpenrouterModelDraft(updated.openrouter_model.value || '');
    } catch (e: any) {
      alert(e.message || 'Failed to save');
      // The sliders update local state optimistically on drag, so a rejected
      // value would otherwise stay on screen as though it had been applied.
      await load();
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading || !config) {
    return (
      <div className="max-w-5xl mx-auto px-4 py-16 text-center text-[var(--text-muted)] text-xs flex items-center justify-center space-x-2">
        <RefreshCw className="w-4 h-4 animate-spin" />
        <span>Loading configuration...</span>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">

      <div className="glass rounded-3xl p-6 shadow-2xl flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center space-x-2.5">
            <div className="w-8 h-8 rounded-xl bg-accent-600/20 border border-accent-500/30 flex items-center justify-center text-accent-500 dark:text-accent-400">
              <Sliders className="w-5 h-5 text-accent-500 dark:text-accent-400" />
            </div>
            <h1 className="text-lg font-extrabold text-[var(--text)] tracking-tight">RAG Configuration</h1>
          </div>
          <p className="text-xs text-[var(--text-muted)] mt-1">
            Live-editable retrieval and generation settings - changes apply to the next chat turn immediately.
          </p>
        </div>

        <button
          onClick={() => save({ reset_system_prompt: true })}
          disabled={isSaving}
          className="flex items-center space-x-1.5 text-xs font-bold text-[var(--text-secondary)] hover:text-[var(--text)] bg-[var(--bg-inset)] hover:bg-[var(--bg-inset)]/70 px-4 py-2.5 rounded-2xl border border-accent-500/20 transition-all cursor-pointer shadow-md shrink-0"
        >
          <RotateCcw className="w-3.5 h-3.5 text-accent-500 dark:text-accent-400" />
          <span>Reset System Prompt</span>
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">

        <div className="glass rounded-3xl p-6 space-y-5 shadow-2xl">
          <div className="flex items-center space-x-2 border-b border-accent-500/10 pb-3.5">
            <Layers className="w-5 h-5 text-accent-500 dark:text-accent-400" />
            <h2 className="text-sm font-extrabold text-[var(--text)]">Retrieval</h2>
          </div>

          <div className="space-y-2">
            <div className="flex justify-between text-xs">
              <label className="font-bold text-[var(--text-secondary)]">Retrieval pool size (before rerank)</label>
              <span className="font-mono text-accent-500 dark:text-accent-400 font-extrabold">{config.retrieval_top_k.value}</span>
            </div>
            <input
              type="range"
              min={4}
              max={30}
              step={1}
              value={config.retrieval_top_k.value}
              onChange={(e) => setConfig({ ...config, retrieval_top_k: { ...config.retrieval_top_k, value: Number(e.target.value) } })}
              onMouseUp={(e) => save({ retrieval_top_k: Number((e.target as HTMLInputElement).value) })}
              onTouchEnd={(e) => save({ retrieval_top_k: Number((e.target as HTMLInputElement).value) })}
              className="w-full accent-accent-500 bg-[var(--bg-subtle)] rounded-lg cursor-pointer"
            />
          </div>

          <div className="space-y-2">
            <div className="flex justify-between text-xs">
              <label className="font-bold text-[var(--text-secondary)]">Chunks sent to LLM (after rerank)</label>
              <span className="font-mono text-accent-500 dark:text-accent-400 font-extrabold">{config.rerank_top_k.value}</span>
            </div>
            {/* Capped by the retrieval pool: reranking only narrows what was
                retrieved, so a higher value is meaningless and the API rejects
                it. Bounding the slider keeps the UI from offering the state. */}
            <input
              type="range"
              min={1}
              max={Math.min(10, config.retrieval_top_k.value)}
              step={1}
              value={config.rerank_top_k.value}
              onChange={(e) => setConfig({ ...config, rerank_top_k: { ...config.rerank_top_k, value: Number(e.target.value) } })}
              onMouseUp={(e) => save({ rerank_top_k: Number((e.target as HTMLInputElement).value) })}
              onTouchEnd={(e) => save({ rerank_top_k: Number((e.target as HTMLInputElement).value) })}
              className="w-full accent-accent-500 bg-[var(--bg-subtle)] rounded-lg cursor-pointer"
            />
          </div>

          <div className="space-y-2">
            <div className="flex justify-between text-xs">
              <label className="font-bold text-[var(--text-secondary)]">Conversation history window (turns)</label>
              <span className="font-mono text-accent-500 dark:text-accent-400 font-extrabold">{config.conversation_history_window.value}</span>
            </div>
            <input
              type="range"
              min={0}
              max={30}
              step={2}
              value={config.conversation_history_window.value}
              onChange={(e) => setConfig({ ...config, conversation_history_window: { ...config.conversation_history_window, value: Number(e.target.value) } })}
              onMouseUp={(e) => save({ conversation_history_window: Number((e.target as HTMLInputElement).value) })}
              onTouchEnd={(e) => save({ conversation_history_window: Number((e.target as HTMLInputElement).value) })}
              className="w-full accent-accent-500 bg-[var(--bg-subtle)] rounded-lg cursor-pointer"
            />
          </div>

          {/* llm_provider is live-editable - it takes effect on the next chat
              turn, no restart, since graph/nodes.py re-checks it on every
              call (see api/routes_admin.py's ConfigOut.llm_provider note). */}
          <div className="space-y-1 pt-2 border-t border-accent-500/10">
            <div className="flex items-center justify-between">
              <label className="text-xs font-bold text-[var(--text-secondary)]">LLM provider</label>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-accent-500/10 text-accent-600 dark:text-accent-300 border border-accent-500/25">
                {config.chat_model.value}
              </span>
            </div>
            <select
              value={config.llm_provider.value}
              onChange={(e) => save({ llm_provider: e.target.value })}
              className="w-full glass-well rounded-2xl p-2.5 text-xs text-[var(--text)] focus:outline-none focus:border-accent-500 cursor-pointer"
            >
              {ALLOWED_LLM_PROVIDERS.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
            <p className="text-[11px] text-[var(--text-faint)] italic">{config.llm_provider.note}</p>
          </div>

          {/* Only a live control when Gemini is the active provider. Under a
              different provider gemini_model is stored but never read, so
              rendering an editable dropdown would claim a switch that does
              nothing. */}
          <div className="space-y-1">
            <label className="text-xs font-bold text-[var(--text-secondary)]">Gemini model</label>
            {config.gemini_model.read_only ? (
              <div className="w-full glass-well rounded-2xl p-2.5 text-xs font-mono text-[var(--text-muted)] flex items-center gap-2">
                <Lock className="w-3.5 h-3.5 shrink-0" />
                <span className="truncate">{config.gemini_model.value}</span>
              </div>
            ) : (
              <select
                value={config.gemini_model.value}
                onChange={(e) => save({ gemini_model: e.target.value })}
                className="w-full glass-well rounded-2xl p-2.5 text-xs text-[var(--text)] focus:outline-none focus:border-accent-500 cursor-pointer"
              >
                {ALLOWED_GEMINI_MODELS.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
            )}
            <p className="text-[11px] text-[var(--text-faint)] italic">{config.gemini_model.note}</p>
          </div>

          {/* openrouter_model has no fixed allowlist (OpenRouter's catalog
              changes too often to hardcode) - free text, saved on blur
              rather than every keystroke. */}
          <div className="space-y-1">
            <label className="text-xs font-bold text-[var(--text-secondary)]">OpenRouter model</label>
            {config.openrouter_model.read_only ? (
              <div className="w-full glass-well rounded-2xl p-2.5 text-xs font-mono text-[var(--text-muted)] flex items-center gap-2">
                <Lock className="w-3.5 h-3.5 shrink-0" />
                <span className="truncate">{config.openrouter_model.value || '(not set)'}</span>
              </div>
            ) : (
              <input
                type="text"
                value={openrouterModelDraft}
                onChange={(e) => setOpenrouterModelDraft(e.target.value)}
                onBlur={() => {
                  if (openrouterModelDraft.trim() && openrouterModelDraft !== config.openrouter_model.value) {
                    save({ openrouter_model: openrouterModelDraft.trim() });
                  }
                }}
                placeholder="e.g. google/gemma-4-31b-it:free"
                className="w-full glass-well rounded-2xl p-2.5 text-xs font-mono text-[var(--text)] focus:outline-none focus:border-accent-500"
              />
            )}
            <p className="text-[11px] text-[var(--text-faint)] italic">{config.openrouter_model.note}</p>
          </div>
        </div>

        <div className="glass rounded-3xl p-6 space-y-4 shadow-2xl">
          <div className="flex items-center space-x-2 border-b border-accent-500/10 pb-3.5">
            <Lock className="w-5 h-5 text-[var(--text-muted)]" />
            <h2 className="text-sm font-extrabold text-[var(--text)]">Read-only (requires re-embedding)</h2>
          </div>

          {[
            ['Embedding provider', config.embedding_provider],
            ['Embedding model', config.embedding_model],
            ['Reranker model', config.reranker_model],
            ['Chunk size', config.chunk_size],
            ['Chunk overlap', config.chunk_overlap],
          ].map(([label, field]: any) => (
            <div key={label} className="flex items-center justify-between text-xs glass-well p-3 rounded-2xl">
              <span className="font-bold text-[var(--text-secondary)]">{label}</span>
              <span className="font-mono text-[var(--text-muted)]">{String(field.value)}</span>
            </div>
          ))}
          {config.chunk_size.note && (
            <p className="text-[11px] text-[var(--text-faint)] italic">{config.chunk_size.note}</p>
          )}
        </div>

      </div>

      <div className="glass rounded-3xl p-6 space-y-4 shadow-2xl">
        <div className="flex items-center justify-between border-b border-accent-500/10 pb-3.5 gap-3">
          <div className="flex items-center space-x-2">
            <Sparkles className="w-5 h-5 text-accent-500 dark:text-accent-400 shrink-0" />
            <div>
              <h2 className="text-sm font-extrabold text-[var(--text)]">System Prompt</h2>
              <p className="text-[11px] text-[var(--text-muted)]">
                {systemPrompt
                  ? 'A custom prompt is active - the default below is not in use.'
                  : 'The default prompt below is active. Anything you write here replaces it.'}
              </p>
            </div>
          </div>
          <span className={`text-[10px] font-extrabold uppercase tracking-wide px-2.5 py-1 rounded-full border shrink-0 ${
            systemPrompt
              ? 'bg-amber-500/15 text-amber-600 dark:text-amber-300 border-amber-500/30'
              : 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-300 border-emerald-500/30'
          }`}>
            {systemPrompt ? 'custom' : 'default'}
          </span>
        </div>

        {/* The override box used to be an empty field asking the admin to
            replace a prompt they had no way to read. Showing the default makes
            the empty state legible and gives a starting point to edit from. */}
        <details className="glass-well rounded-2xl overflow-hidden">
          <summary className="cursor-pointer px-4 py-3 text-xs font-bold text-[var(--text-secondary)] hover:text-[var(--text)] flex items-center gap-2">
            <Eye className="w-3.5 h-3.5 text-accent-500 dark:text-accent-400" />
            View the default prompt
            <span className="font-normal text-[var(--text-muted)]">
              ({config.default_system_prompt.value.length.toLocaleString()} characters)
            </span>
          </summary>
          <div className="px-4 pb-4 space-y-3">
            <pre className="text-[11px] font-mono text-[var(--text-muted)] whitespace-pre-wrap leading-relaxed max-h-72 overflow-y-auto">
              {config.default_system_prompt.value}
            </pre>
            <button
              type="button"
              onClick={() => setSystemPrompt(config.default_system_prompt.value)}
              className="flex items-center space-x-1.5 text-[11px] font-bold text-[var(--text-secondary)] hover:text-[var(--text)] bg-[var(--bg-inset)] px-3.5 py-2 rounded-xl border border-accent-500/20 transition-all cursor-pointer"
            >
              <Copy className="w-3.5 h-3.5 text-accent-500 dark:text-accent-400" />
              <span>Copy into the editor to modify it</span>
            </button>
          </div>
        </details>

        <textarea
          rows={8}
          value={systemPrompt}
          onChange={(e) => setSystemPrompt(e.target.value)}
          placeholder="Empty - the default prompt above is in use. Write here to replace it."
          className="w-full glass-well rounded-2xl p-4 text-xs font-mono text-[var(--text-secondary)] focus:outline-none focus:border-accent-500/60 leading-relaxed"
        />

        <div className="flex justify-end">
          <button
            onClick={() => save({ system_prompt_override: systemPrompt || undefined, reset_system_prompt: !systemPrompt })}
            disabled={isSaving}
            className="flex items-center space-x-2 bg-gradient-to-r from-accent-600 to-accent-700 hover:from-accent-500 hover:to-accent-600 text-[var(--text)] text-xs font-bold px-5 py-2.5 rounded-2xl shadow-lg shadow-accent-600/30 border border-accent-400/30 transition-all cursor-pointer disabled:opacity-50"
          >
            <Save className="w-4 h-4" />
            <span>{isSaving ? 'Saving...' : 'Save Prompt'}</span>
          </button>
        </div>
      </div>

    </div>
  );
};
