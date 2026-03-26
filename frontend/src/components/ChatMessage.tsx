import { useState } from "react";
import ReactMarkdown from "react-markdown";
import type { ChatMessage as ChatMessageType } from "../state/chatStore";
import type { GaiaDocument } from "../api/gaia";
import { API_URL, buildHeaders } from "../api/client";

interface Props {
  message: ChatMessageType;
}

function SourcesTab({ docs }: { docs: GaiaDocument[] }) {
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  async function handleDownload(doc: GaiaDocument) {
    const id = doc.uid ?? doc.documentId;
    if (!id) return;
    setDownloadingId(id);
    try {
      const resp = await fetch(
        `${API_URL}/documents/${encodeURIComponent(id)}/download`,
        { headers: buildHeaders() }
      );
      if (!resp.ok) throw new Error(`${resp.status}`);
      const { downloadUrl } = await resp.json();
      window.open(downloadUrl, "_blank", "noopener,noreferrer");
    } catch {
      alert("Download link unavailable for this file.");
    } finally {
      setDownloadingId(null);
    }
  }

  return (
    <ul className="citations-list">
      {docs.map((doc, i) => {
        const label = doc.name ?? doc.documentId ?? `Document ${i + 1}`;
        const snippet = doc.citations?.[0]?.textSnippet;
        const score = doc.citations?.[0]?.cosineScore;
        const id = doc.uid ?? doc.documentId;
        const isLoading = downloadingId === id;
        return (
          <li key={doc.documentId ?? doc.uid ?? i} className="citation-item">
            <span className="citation-index">{i + 1}</span>
            <div className="citation-content">
              <div className="citation-header">
                <span className="citation-name" title={doc.absolutePath ?? undefined}>
                  {label}
                </span>
                <button
                  className="citation-download-btn"
                  onClick={() => handleDownload(doc)}
                  disabled={isLoading}
                  title="Download file"
                >
                  {isLoading ? "…" : "↓"}
                </button>
              </div>
              {score !== undefined && (
                <span className="citation-score">
                  {Math.round(score * 100)}% match
                </span>
              )}
              {snippet && (
                <p className="citation-snippet">{snippet}</p>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

export default function ChatMessage({ message }: Props) {
  const isUser = message.role === "user";
  const docs = message.documents ?? [];
  const [activeTab, setActiveTab] = useState<"answer" | "sources">("answer");

  if (isUser) {
    return (
      <div className="chat-message user">
        <div className="message-avatar">You</div>
        <div className="message-body">
          <p>{message.content}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="chat-message assistant">
      <div className="message-avatar">AI</div>
      <div className="message-body message-body--tabbed">
        {docs.length > 0 && (
          <div className="msg-tabs">
            <button
              className={`msg-tab ${activeTab === "answer" ? "msg-tab--active" : ""}`}
              onClick={() => setActiveTab("answer")}
            >
              Answer
            </button>
            <button
              className={`msg-tab ${activeTab === "sources" ? "msg-tab--active" : ""}`}
              onClick={() => setActiveTab("sources")}
            >
              Sources
              <span className="msg-tab-badge">{docs.length}</span>
            </button>
          </div>
        )}

        {activeTab === "answer" || !docs.length ? (
          <div className="msg-tab-content">
            <ReactMarkdown>{message.content || "…"}</ReactMarkdown>
          </div>
        ) : (
          <div className="msg-tab-content">
            <SourcesTab docs={docs} />
          </div>
        )}
      </div>
    </div>
  );
}
