import { useEffect, useState } from "react";
import {
  approveSubmission,
  fetchPendingSubmissions,
  rejectSubmission,
  uploadDocument,
} from "../api/client";
import { CheckIcon, FileIcon, ShieldIcon, UploadIcon, XIcon } from "../components/Icons";

export default function AdminPage() {
  const [submissions, setSubmissions] = useState([]);
  const [error, setError] = useState(null);
  const [uploadStatus, setUploadStatus] = useState(null);

  async function refresh() {
    try {
      const data = await fetchPendingSubmissions();
      setSubmissions(data);
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function handleApprove(id) {
    await approveSubmission(id);
    refresh();
  }

  async function handleReject(id) {
    await rejectSubmission(id);
    refresh();
  }

  async function handleUpload(event) {
    event.preventDefault();
    const file = event.target.elements.file.files[0];
    if (!file) return;

    setUploadStatus("Uploading...");
    try {
      const result = await uploadDocument(file);
      setUploadStatus(`Ingested ${result.chunks_ingested} chunks from ${result.filename}`);
    } catch (err) {
      setUploadStatus(`Upload failed: ${err.message}`);
    }
  }

  return (
    <div className="admin-page">
      <div className="admin-header">
        <span className="admin-header-badge">
          <ShieldIcon />
        </span>
        <div>
          <h1>Admin panel</h1>
          <p className="admin-subtitle">Manage documents and review user contributions</p>
        </div>
      </div>

      <section className="panel">
        <h2>
          <UploadIcon /> Upload document
        </h2>
        <form onSubmit={handleUpload} className="upload-form">
          <input
            type="file"
            name="file"
            accept=".pdf,.md,.txt,.docx,.xlsx,.pptx,.html,.htm,.csv"
            required
          />
          <button type="submit">Upload</button>
        </form>
        {uploadStatus && (
          <p className="upload-status">
            <FileIcon /> {uploadStatus}
          </p>
        )}
      </section>

      <section className="panel">
        <h2>Pending submissions</h2>
        {error && <p className="error">{error}</p>}
        {submissions.length === 0 && <p className="empty-panel-note">No pending submissions.</p>}
        <ul className="submission-list">
          {submissions.map((s) => (
            <li key={s.id} className="submission-item">
              <div className="submission-meta">
                <span className={`badge badge-${s.submission_type}`}>
                  {s.submission_type === "correction" ? "Correction" : "New info"}
                </span>
                <span className="submission-source">source: {s.source_id}</span>
              </div>
              <p className="submission-content">{s.content}</p>
              <div className="submission-actions">
                <button type="button" className="button-success" onClick={() => handleApprove(s.id)}>
                  <CheckIcon /> Approve
                </button>
                <button type="button" className="button-danger" onClick={() => handleReject(s.id)}>
                  <XIcon /> Reject
                </button>
              </div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
