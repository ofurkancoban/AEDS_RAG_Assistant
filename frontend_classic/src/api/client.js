const API_BASE_URL = "http://localhost:8000";

function getToken() {
  return localStorage.getItem("access_token");
}

async function request(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  const token = getToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${response.status}`);
  }
  if (response.status === 204) return null;
  return response.json();
}

export async function login(email, password) {
  const form = new URLSearchParams();
  form.set("username", email);
  form.set("password", password);

  const response = await fetch(`${API_BASE_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: form,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || "Login failed");
  }
  return response.json();
}

export function register(email, password) {
  return request("/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
}

export function sendChatMessage(message, threadId, sourceIdFilter) {
  return request("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      thread_id: threadId,
      source_id_filter: sourceIdFilter,
    }),
  });
}

// Parses one Server-Sent-Events "event: X\ndata: Y\n\n" block into {event, data}.
function parseSseEvent(block) {
  let event = "message";
  let data = "";
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data += line.slice(5).trim();
  }
  return { event, data: data ? JSON.parse(data) : null };
}

// Streams a chat answer token-by-token via SSE. onToken(text) is called for
// each token as it arrives; onDone({thread_id, sources, auto_flagged_contribution})
// is called once when the stream ends.
export async function streamChatMessage(message, threadId, sourceIdFilter, { onToken, onDone }) {
  const headers = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(`${API_BASE_URL}/chat/stream`, {
    method: "POST",
    headers,
    body: JSON.stringify({ message, thread_id: threadId, source_id_filter: sourceIdFilter }),
  });
  if (!response.ok || !response.body) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let separatorIndex;
    while ((separatorIndex = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, separatorIndex);
      buffer = buffer.slice(separatorIndex + 2);
      if (!block.trim()) continue;

      const { event, data } = parseSseEvent(block);
      if (event === "token" && data) onToken(data.text);
      else if (event === "done" && data) onDone(data);
    }
  }
}

export function submitFeedback(payload) {
  return request("/chat/submissions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function fetchPendingSubmissions() {
  return request("/admin/pending");
}

export function approveSubmission(id, adminNote) {
  return request(`/admin/pending/${id}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ admin_note: adminNote || null }),
  });
}

export function rejectSubmission(id, adminNote) {
  return request(`/admin/pending/${id}/reject`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ admin_note: adminNote || null }),
  });
}

export function uploadDocument(file) {
  const formData = new FormData();
  formData.append("file", file);
  return request("/admin/documents", { method: "POST", body: formData });
}

