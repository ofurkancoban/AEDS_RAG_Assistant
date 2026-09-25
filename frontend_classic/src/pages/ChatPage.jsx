import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { streamChatMessage, submitFeedback } from "../api/client";
import { EditIcon, FileIcon, LinkIcon, PlusIcon, SendIcon, SparkleIcon } from "../components/Icons";

const SUGGESTED_QUESTIONS = [
  "What are the admission requirements?",
  "What courses are in the curriculum?",
  "How and when do I apply?",
];

function sourceLabel(source) {
  const name = source.source_id.replace(/[_-]+/g, " ").trim();
  return source.page != null ? `${name} · p.${source.page}` : name;
}

export default function ChatPage() {
  const [turns, setTurns] = useState([]);
  const [input, setInput] = useState("");
  const [threadId, setThreadId] = useState(null);
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [feedbackType, setFeedbackType] = useState("correction");
  const [feedbackText, setFeedbackText] = useState("");
  const [sending, setSending] = useState(false);
  const nextIdRef = useRef(0);
  const scrollRef = useRef(null);

  // Keeps the feed pinned to the latest message - fires on every new turn and
  // on every streamed token, since each token update replaces the turns array.
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [turns]);

  async function ask(question) {
    if (!question.trim() || sending) return;

    const turnId = nextIdRef.current++;
    setTurns((prev) => [
      ...prev,
      { id: turnId, question, answer: "", sources: [], autoFlagged: null, streaming: true, error: null },
    ]);
    setInput("");
    setSending(true);

    function updateTurn(patch) {
      setTurns((prev) => prev.map((t) => (t.id === turnId ? { ...t, ...patch(t) } : t)));
    }

    try {
      await streamChatMessage(question, threadId, null, {
        onToken: (text) => updateTurn((t) => ({ answer: t.answer + text })),
        onDone: (data) => {
          setThreadId(data.thread_id);
          updateTurn((t) => ({
            answer: data.final_answer ?? t.answer,
            sources: data.sources || [],
            autoFlagged: data.auto_flagged_contribution || null,
            streaming: false,
          }));
        },
      });
    } catch (err) {
      updateTurn(() => ({ streaming: false, error: err.message }));
    } finally {
      setSending(false);
    }
  }

  function handleSend(event) {
    event.preventDefault();
    ask(input);
  }

  function openFeedback(type) {
    setFeedbackType(type);
    setFeedbackText("");
    setFeedbackOpen(true);
  }

  async function handleFeedbackSubmit(event) {
    event.preventDefault();
    try {
      await submitFeedback({
        submission_type: feedbackType,
        source_id: "general",
        content: feedbackText,
        related_chunk_id: null,
      });
      setFeedbackOpen(false);
      alert("Your contribution has been sent for admin review.");
    } catch (err) {
      alert(`Submission failed: ${err.message}`);
    }
  }

  return (
    <div className="chat-page">
      <header className="chat-header">
        <h1>Applied Economics &amp; Data Science</h1>
        <p>Study programme assistant</p>
      </header>

      <div className="chat-scroll" ref={scrollRef}>
        {turns.length === 0 ? (
          <div className="empty-state">
            <p className="empty-state-lead">
              Ask a question about admission, curriculum, deadlines, or careers for this
              programme. Every answer is grounded in the official programme documents,
              with sources shown below it.
            </p>
            <div className="suggestion-row">
              {SUGGESTED_QUESTIONS.map((q) => (
                <button key={q} type="button" className="suggestion-chip" onClick={() => ask(q)}>
                  <SparkleIcon /> {q}
                </button>
              ))}
            </div>
            <button type="button" className="link-button add-info-link" onClick={() => openFeedback("new_info")}>
              <PlusIcon /> Add information about this programme
            </button>
          </div>
        ) : (
          <div className="answer-feed">
            {turns.map((turn) => (
              <div key={turn.id} className="turn">
                <div className="question-row">
                  <div className="question-bubble">{turn.question}</div>
                </div>

                <div className="answer-row">
                  <span className="answer-avatar">
                    <SparkleIcon />
                  </span>
                  <article className="answer-card">
                    {turn.error ? (
                      <p className="error">{turn.error}</p>
                    ) : turn.streaming && !turn.answer ? (
                      <span className="typing-dots">
                        <span className="typing-dot" />
                        <span className="typing-dot" />
                        <span className="typing-dot" />
                      </span>
                    ) : (
                      <div className="markdown-content">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{turn.answer}</ReactMarkdown>
                      </div>
                    )}

                    {turn.autoFlagged && (
                      <p className="auto-flag-note">
                        <EditIcon /> We noticed your previous message looked like{" "}
                        {turn.autoFlagged === "correction" ? "a correction" : "new information"} and sent
                        it for admin review.
                      </p>
                    )}

                    {!turn.streaming && !turn.error && (
                      <footer className="answer-footer">
                        {turn.sources.length > 0 && (
                          <div className="source-list">
                            {turn.sources.map((source, i) =>
                              source.url ? (
                                <a
                                  key={i}
                                  className="source-chip"
                                  href={source.url}
                                  target="_blank"
                                  rel="noreferrer"
                                >
                                  <LinkIcon />
                                  <span>{sourceLabel(source)}</span>
                                </a>
                              ) : (
                                <span key={i} className="source-chip">
                                  <FileIcon />
                                  <span>{sourceLabel(source)}</span>
                                </span>
                              )
                            )}
                          </div>
                        )}
                        <div className="footer-actions">
                          <button
                            type="button"
                            className="link-button"
                            onClick={() => openFeedback("correction")}
                          >
                            Correct this answer
                          </button>
                        </div>
                      </footer>
                    )}
                  </article>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="ask-bar-wrap">
        <form onSubmit={handleSend} className="ask-bar">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about the study programme..."
          />
          <button type="submit" className="icon-button" disabled={sending} aria-label="Send">
            <SendIcon />
          </button>
        </form>
      </div>

      {feedbackOpen && (
        <FeedbackModal
          feedbackType={feedbackType}
          feedbackText={feedbackText}
          setFeedbackText={setFeedbackText}
          onSubmit={handleFeedbackSubmit}
          onClose={() => setFeedbackOpen(false)}
        />
      )}
    </div>
  );
}

function FeedbackModal({ feedbackType, feedbackText, setFeedbackText, onSubmit, onClose }) {
  return (
    <div className="modal-overlay">
      <form className="modal" onSubmit={onSubmit}>
        <h2>{feedbackType === "correction" ? "Suggest a correction" : "Add new information"}</h2>
        <textarea
          value={feedbackText}
          onChange={(e) => setFeedbackText(e.target.value)}
          placeholder="Describe what should change or be added..."
          required
        />
        <p className="modal-note">
          <EditIcon /> This contribution is added to the system only after admin review.
        </p>
        <div className="modal-actions">
          <button type="button" className="ghost-button" onClick={onClose}>
            Cancel
          </button>
          <button type="submit">Submit for review</button>
        </div>
      </form>
    </div>
  );
}
