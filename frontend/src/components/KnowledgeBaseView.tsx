import React, { useEffect, useState } from 'react';
import {
  FileText, Trash2, Search, Upload, RefreshCw,
  CheckCircle2, Database, Loader2, Info, Files, X,
  AlertTriangle, ExternalLink, Check,
} from 'lucide-react';
import { IngestedDocumentInfo, SourceChange } from '../types';
import {
  approveSourceDraft, deleteDocument, dismissSourceChange, listDocuments, listSourceChanges,
  rejectSourceDraft, uploadDocument,
} from '../api/client';

/** Renders scripts/source_refresh.py's word-level diff ('[-removed]' /
    '[+added]' tokens inline) as colored spans instead of raw brackets. */
const DiffPreview: React.FC<{ diff: string }> = ({ diff }) => {
  const parts = diff.split(/(\[-[^\]]*\]|\[\+[^\]]*\])/g).filter(Boolean);
  return (
    <p className="text-[11px] font-mono leading-relaxed break-words">
      {parts.map((part, idx) => {
        if (part.startsWith('[-')) {
          return (
            <span key={idx} className="bg-rose-500/15 text-rose-600 dark:text-rose-300 line-through decoration-rose-500/60 px-0.5 rounded">
              {part.slice(2, -1)}
            </span>
          );
        }
        if (part.startsWith('[+')) {
          return (
            <span key={idx} className="bg-emerald-500/15 text-emerald-600 dark:text-emerald-300 px-0.5 rounded">
              {part.slice(2, -1)}
            </span>
          );
        }
        return <span key={idx} className="text-[var(--text-muted)]">{part}</span>;
      })}
    </p>
  );
};

interface BulkStatus {
  total: number;
  current: number;
  currentFileName: string;
  isBulkUploading: boolean;
  successCount: number;
  /** Files the server skipped because their content was already indexed. */
  unchangedCount: number;
  errors: string[];
}

const SUPPORTED_FORMATS = [
  { label: 'PDF Documents', ext: '.pdf' },
  { label: 'Word Documents', ext: '.docx' },
  { label: 'Excel Sheets', ext: '.xlsx' },
  { label: 'PowerPoint', ext: '.pptx' },
  { label: 'HTML Webpages', ext: '.html, .htm' },
  { label: 'Markdown', ext: '.md' },
  { label: 'CSV Spreadsheets', ext: '.csv' },
  { label: 'Plain Text', ext: '.txt' },
];

interface KnowledgeBaseViewProps {
  /** Lets the navbar's chunk/document counters refresh after an ingest or
      delete, instead of staying stale until a full page reload. */
  onCorpusChange?: () => void;
}

export const KnowledgeBaseView: React.FC<KnowledgeBaseViewProps> = ({ onCorpusChange }) => {
  const [documents, setDocuments] = useState<IngestedDocumentInfo[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isAddingNew, setIsAddingNew] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [bulkStatus, setBulkStatus] = useState<BulkStatus | null>(null);

  const [sourceChanges, setSourceChanges] = useState<SourceChange[]>([]);
  const [isLoadingChanges, setIsLoadingChanges] = useState(false);
  const [dismissingFilename, setDismissingFilename] = useState<string | null>(null);
  // Separate from dismissingFilename: approve/reject act on the draft only
  // (see SourceChange.draft), a different, narrower action than dismissing
  // the whole change, and a source can only ever have one in flight at once.
  const [draftActionFilename, setDraftActionFilename] = useState<string | null>(null);

  const load = async () => {
    setIsLoading(true);
    try {
      const data = await listDocuments();
      setDocuments(data);
    } catch (e) {
      console.error('Failed to load documents:', e);
    } finally {
      setIsLoading(false);
    }
  };

  const loadSourceChanges = async () => {
    setIsLoadingChanges(true);
    try {
      const data = await listSourceChanges();
      setSourceChanges(data);
    } catch (e) {
      console.error('Failed to load source changes:', e);
    } finally {
      setIsLoadingChanges(false);
    }
  };

  useEffect(() => {
    load();
    loadSourceChanges();
  }, []);

  const handleDismissChange = async (filename: string) => {
    setDismissingFilename(filename);
    try {
      await dismissSourceChange(filename);
      setSourceChanges((prev) => prev.filter((c) => c.filename !== filename));
      onCorpusChange?.();
    } catch (e: any) {
      alert(e.message || 'Failed to dismiss');
    } finally {
      setDismissingFilename(null);
    }
  };

  const handleApproveDraft = async (filename: string) => {
    setDraftActionFilename(filename);
    try {
      await approveSourceDraft(filename);
      // The draft is now the curated file on disk, and re-ingested - the
      // whole change (diff + draft) is resolved, same as a dismiss.
      setSourceChanges((prev) => prev.filter((c) => c.filename !== filename));
      onCorpusChange?.();
      load();
    } catch (e: any) {
      alert(e.message || 'Failed to approve draft');
    } finally {
      setDraftActionFilename(null);
    }
  };

  const handleRejectDraft = async (filename: string) => {
    setDraftActionFilename(filename);
    try {
      await rejectSourceDraft(filename);
      // Only the draft is gone - the plain change stays, so it keeps
      // showing here for the ordinary manual-dismiss review below.
      setSourceChanges((prev) =>
        prev.map((c) => (c.filename === filename ? { ...c, draft: null } : c))
      );
    } catch (e: any) {
      alert(e.message || 'Failed to reject draft');
    } finally {
      setDraftActionFilename(null);
    }
  };

  const filteredDocs = documents.filter((d) => d.filename.toLowerCase().includes(searchQuery.toLowerCase()));

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const filesList = e.target.files;
    if (!filesList || filesList.length === 0) return;
    const files = Array.from(filesList);

    setBulkStatus({
      total: files.length, current: 0, currentFileName: '', isBulkUploading: true,
      successCount: 0, unchangedCount: 0, errors: [],
    });

    let succCount = 0;
    let unchangedCount = 0;
    const errorsList: string[] = [];

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      setBulkStatus((prev) => (prev ? { ...prev, current: i + 1, currentFileName: file.name } : null));
      try {
        const result = await uploadDocument(file);
        if (result.unchanged) unchangedCount++;
        else succCount++;
      } catch (err: any) {
        errorsList.push(`${file.name}: ${err?.message || 'Upload failed'}`);
      }
    }

    setBulkStatus((prev) =>
      prev ? { ...prev, isBulkUploading: false, successCount: succCount, unchangedCount, errors: errorsList } : null
    );
    e.target.value = '';
    await load();
    onCorpusChange?.();
  };

  const handleDelete = async (filename: string) => {
    if (!confirm(`Delete "${filename}" and remove its indexed content?`)) return;
    try {
      await deleteDocument(filename);
      await load();
      onCorpusChange?.();
    } catch (e: any) {
      alert(e.message || 'Failed to delete');
    }
  };

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">

      <div className="glass rounded-3xl p-6 shadow-2xl space-y-4">
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 border-b border-accent-500/10 pb-4">
          <div className="space-y-1">
            <div className="flex items-center space-x-2.5">
              <div className="w-8 h-8 rounded-xl bg-accent-600/20 border border-accent-500/30 flex items-center justify-center text-accent-500 dark:text-accent-400">
                <Database className="w-5 h-5" />
              </div>
              <h1 className="text-lg font-extrabold text-[var(--text)] tracking-tight">Document Ingestion &amp; Knowledge Base</h1>
            </div>
            <p className="text-xs text-[var(--text-secondary)]">
              Upload documents to be chunked, embedded, and indexed for retrieval.
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
              onClick={() => setIsAddingNew(true)}
              className="flex-1 md:flex-none flex items-center justify-center space-x-2 bg-gradient-to-r from-accent-600 to-accent-700 hover:from-accent-500 hover:to-accent-600 text-white text-xs font-bold px-4.5 py-2.5 rounded-2xl shadow-lg shadow-accent-600/30 border border-accent-400/30 transition-all cursor-pointer"
            >
              <Files className="w-4 h-4" />
              <span>Upload Documents</span>
            </button>
          </div>
        </div>

        <div className="space-y-2">
          <div className="flex items-center space-x-2 text-xs font-bold text-accent-600 dark:text-accent-300">
            <Info className="w-3.5 h-3.5 text-accent-500 dark:text-accent-400" />
            <span>Supported Formats:</span>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-8 gap-2">
            {SUPPORTED_FORMATS.map((fmt, idx) => (
              <div key={idx} className="p-2.5 rounded-2xl border border-accent-500/15 bg-accent-500/5 flex flex-col text-xs shadow-sm">
                <p className="text-[11px] font-extrabold text-[var(--text-secondary)] leading-tight">{fmt.label}</p>
                <p className="text-[9px] opacity-70 font-mono text-[var(--text-muted)]">{fmt.ext}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {sourceChanges.length > 0 && (
        <div className="glass rounded-3xl p-5 shadow-2xl space-y-3">
          <div className="flex items-center justify-between border-b border-amber-500/10 pb-3">
            <div className="flex items-center space-x-2.5">
              <div className="w-8 h-8 rounded-xl bg-amber-500/15 border border-amber-500/30 flex items-center justify-center text-amber-600 dark:text-amber-400">
                <AlertTriangle className="w-4 h-4" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-[var(--text)]">Source Changes ({sourceChanges.length})</h3>
                <p className="text-[11px] text-[var(--text-muted)]">
                  These source pages changed since curation. Nothing was overwritten, review each and re-curate by hand.
                </p>
              </div>
            </div>
            <button
              onClick={loadSourceChanges}
              className="p-2 text-[var(--text-muted)] hover:text-[var(--text)] hover:bg-[var(--bg-inset)] rounded-xl transition-colors cursor-pointer shrink-0"
              title="Refresh"
            >
              <RefreshCw className={`w-4 h-4 ${isLoadingChanges ? 'animate-spin' : ''}`} />
            </button>
          </div>

          <div className="space-y-2.5 max-h-[400px] overflow-y-auto pr-1">
            {sourceChanges.map((change) => (
              <div key={change.filename} className="p-3.5 rounded-2xl glass-well space-y-2">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className="text-xs font-bold text-[var(--text)] truncate">{change.filename}</span>
                      {change.url && (
                        <a
                          href={change.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-accent-500 dark:text-accent-400 hover:underline inline-flex items-center gap-0.5 text-[10px] font-semibold shrink-0"
                        >
                          source <ExternalLink className="w-2.5 h-2.5" />
                        </a>
                      )}
                    </div>
                    <p className="text-[10px] text-[var(--text-muted)]">
                      changed {new Date(change.last_changed_at).toLocaleString('en-US')}
                      {change.last_checked_at && ` • last checked ${new Date(change.last_checked_at).toLocaleString('en-US')}`}
                    </p>
                  </div>
                  <button
                    onClick={() => handleDismissChange(change.filename)}
                    disabled={dismissingFilename === change.filename}
                    className="flex items-center gap-1 text-[10px] font-bold text-emerald-600 dark:text-emerald-400 hover:bg-emerald-500/10 px-2.5 py-1.5 rounded-xl transition-colors cursor-pointer shrink-0 disabled:opacity-50"
                    title="Mark reviewed"
                  >
                    {dismissingFilename === change.filename
                      ? <Loader2 className="w-3 h-3 animate-spin" />
                      : <Check className="w-3 h-3" />}
                    <span>Dismiss</span>
                  </button>
                </div>
                <div className="bg-[var(--bg-inset)]/60 rounded-xl p-2.5 max-h-32 overflow-y-auto">
                  <DiffPreview diff={change.diff} />
                </div>

                {/* Only the small AUTO_DRAFT_ELIGIBLE allowlist ever has one
                    (see scripts/source_refresh.py) - the same LLM-drafted
                    replacement already offered via Telegram's "Approve
                    draft"/"Reject draft" buttons, mirrored here. */}
                {change.draft && (
                  <div className="rounded-xl border border-accent-500/25 bg-accent-500/5 p-2.5 space-y-2">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[10px] font-bold text-accent-600 dark:text-accent-400 uppercase tracking-wide">
                        Auto-draft ready
                      </span>
                      <div className="flex items-center gap-1.5 shrink-0">
                        <button
                          onClick={() => handleRejectDraft(change.filename)}
                          disabled={draftActionFilename === change.filename}
                          className="flex items-center gap-1 text-[10px] font-bold text-red-600 dark:text-red-400 hover:bg-red-500/10 px-2 py-1 rounded-lg transition-colors cursor-pointer disabled:opacity-50"
                          title="Discard the draft, keep the change flagged for manual review"
                        >
                          <X className="w-3 h-3" />
                          <span>Reject draft</span>
                        </button>
                        <button
                          onClick={() => handleApproveDraft(change.filename)}
                          disabled={draftActionFilename === change.filename}
                          className="flex items-center gap-1 text-[10px] font-bold text-white bg-accent-600 hover:bg-accent-700 px-2 py-1 rounded-lg transition-colors cursor-pointer disabled:opacity-50"
                          title="Write this over the curated file and re-ingest it"
                        >
                          {draftActionFilename === change.filename
                            ? <Loader2 className="w-3 h-3 animate-spin" />
                            : <Check className="w-3 h-3" />}
                          <span>Approve draft</span>
                        </button>
                      </div>
                    </div>
                    <p className="text-[11px] font-mono leading-relaxed whitespace-pre-wrap break-words max-h-40 overflow-y-auto text-[var(--text-secondary)]">
                      {change.draft}
                    </p>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {bulkStatus && (
        <div className="glass rounded-3xl p-5 shadow-2xl space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <Files className="w-5 h-5 text-accent-500 dark:text-accent-400" />
              <h3 className="text-sm font-bold text-[var(--text)]">Upload Progress</h3>
            </div>
            {!bulkStatus.isBulkUploading && (
              <button onClick={() => setBulkStatus(null)} className="text-[var(--text-muted)] hover:text-[var(--text)] p-1 rounded cursor-pointer">
                <X className="w-4 h-4" />
              </button>
            )}
          </div>

          {bulkStatus.isBulkUploading ? (
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs text-[var(--text-secondary)]">
                <span className="flex items-center space-x-2 font-semibold">
                  <Loader2 className="w-4 h-4 animate-spin text-accent-500 dark:text-accent-400" />
                  <span>File {bulkStatus.current} of {bulkStatus.total}: <strong className="text-[var(--text)]">{bulkStatus.currentFileName}</strong></span>
                </span>
              </div>
              <div className="w-full h-2 glass-well rounded-full overflow-hidden">
                <div className="h-full bg-gradient-to-r from-accent-600 to-brass-400 transition-all duration-300" style={{ width: `${(bulkStatus.current / bulkStatus.total) * 100}%` }} />
              </div>
            </div>
          ) : (
            <div className="space-y-2">
              <div className="flex items-center space-x-2 text-xs text-emerald-600 dark:text-emerald-400 font-bold bg-emerald-500/10 border border-emerald-500/20 p-3 rounded-2xl">
                <CheckCircle2 className="w-5 h-5 shrink-0" />
                <span>
                  Indexed {bulkStatus.successCount} of {bulkStatus.total} files.
                  {bulkStatus.unchangedCount > 0 &&
                    ` ${bulkStatus.unchangedCount} already up to date (skipped).`}
                </span>
              </div>
              {bulkStatus.errors.length > 0 && (
                <div className="bg-rose-500/10 border border-rose-500/20 text-rose-600 dark:text-rose-300 p-3 rounded-2xl text-xs space-y-1">
                  {bulkStatus.errors.map((err, idx) => <p key={idx} className="font-mono text-[11px]">• {err}</p>)}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {isAddingNew && (
        <div className="glass rounded-3xl p-6 space-y-4 shadow-2xl">
          <div className="flex items-center justify-between border-b border-accent-500/10 pb-3.5">
            <div className="flex items-center space-x-2">
              <Upload className="w-5 h-5 text-accent-500 dark:text-accent-400" />
              <h2 className="text-sm font-extrabold text-[var(--text)]">Upload Documents</h2>
            </div>
            <button onClick={() => setIsAddingNew(false)} className="text-xs text-[var(--text-muted)] hover:text-[var(--text-secondary)] cursor-pointer font-bold">
              Close
            </button>
          </div>

          <div className="bg-[var(--glass-well-bg)] border-2 border-dashed border-accent-500/25 hover:border-accent-500/60 rounded-2xl p-6 text-center space-y-3 transition-colors relative">
            <input
              type="file"
              multiple
              accept=".pdf,.docx,.xlsx,.pptx,.html,.htm,.md,.txt,.csv"
              onChange={handleFileUpload}
              disabled={bulkStatus?.isBulkUploading || false}
              className="absolute inset-0 opacity-0 w-full h-full cursor-pointer z-10"
            />
            <div className="w-12 h-12 bg-accent-500/10 border border-accent-500/20 rounded-2xl flex items-center justify-center mx-auto text-accent-500 dark:text-accent-400 shadow-md">
              {bulkStatus?.isBulkUploading ? <Loader2 className="w-6 h-6 animate-spin" /> : <Files className="w-6 h-6" />}
            </div>
            <p className="text-xs font-bold text-[var(--text)]">Click or drop file(s) here</p>
            <p className="text-[11px] text-[var(--text-muted)]">Each file is uploaded, chunked, embedded, and indexed on the server.</p>
          </div>
        </div>
      )}

      <div className="glass rounded-3xl p-4 space-y-4 shadow-2xl">
        <div className="relative">
          <Search className="w-4 h-4 text-[var(--text-faint)] absolute left-3.5 top-3" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search documents..."
            className="w-full glass-well rounded-2xl pl-10 pr-3 py-2 text-xs text-[var(--text-secondary)] focus:outline-none focus:border-accent-500 font-medium"
          />
        </div>

        <div className="text-xs font-extrabold text-accent-500 dark:text-accent-400 uppercase tracking-wider px-1">
          Ingested Documents ({filteredDocs.length})
        </div>

        {filteredDocs.length === 0 ? (
          <div className="py-12 text-center text-[var(--text-faint)] text-xs">
            {isLoading ? 'Loading...' : 'No documents ingested yet.'}
          </div>
        ) : (
          <div className="space-y-2 max-h-[550px] overflow-y-auto pr-1">
            {filteredDocs.map((doc) => (
              <div key={doc.filename} className="p-3.5 rounded-2xl glass-well flex items-center justify-between">
                <div className="flex items-center space-x-2.5 overflow-hidden">
                  <FileText className="w-4 h-4 text-accent-500 dark:text-accent-400 shrink-0" />
                  <div className="truncate">
                    <h4 className="text-xs font-bold text-[var(--text)] truncate flex items-center gap-1.5">
                      <span className="truncate">{doc.filename}</span>
                      {doc.expired && (
                        <span className="shrink-0 text-[9px] font-extrabold uppercase tracking-wide px-1.5 py-0.5 rounded-full bg-amber-500/15 text-amber-600 dark:text-amber-300 border border-amber-500/30">
                          expired
                        </span>
                      )}
                    </h4>
                    <div className="flex items-center space-x-2 text-[10px] text-[var(--text-muted)]">
                      <span className="text-accent-500 dark:text-accent-300 font-mono font-bold">{doc.chunk_count} chunks</span>
                      <span>•</span>
                      <span>{new Date(doc.ingested_at).toLocaleString('en-US')}</span>
                      {doc.valid_until && (
                        <>
                          <span>•</span>
                          <span className={doc.expired ? 'text-amber-600 dark:text-amber-400 font-bold' : ''}>
                            valid until {new Date(doc.valid_until).toLocaleDateString('en-US')}
                          </span>
                        </>
                      )}
                    </div>
                  </div>
                </div>
                <button
                  onClick={() => handleDelete(doc.filename)}
                  className="p-1.5 text-[var(--text-faint)] hover:text-rose-500 hover:bg-[var(--bg-inset)] rounded-xl transition-colors ml-2 cursor-pointer shrink-0"
                  title="Delete document"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

    </div>
  );
};
