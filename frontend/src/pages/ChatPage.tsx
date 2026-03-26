import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useSessionStore } from "../state/sessionStore";
import { useChatStore } from "../state/chatStore";
import DatasetSelector from "../components/DatasetSelector";
import ChatMessage from "../components/ChatMessage";
import ChatInput from "../components/ChatInput";
import TopicExplorer from "../components/TopicExplorer";
import TopicOverview from "../components/TopicOverview";
import DatasetManager from "../components/DatasetManager";

export default function ChatPage() {
  const navigate = useNavigate();
  const logout = useSessionStore((s) => s.logout);
  const { messages, isLoading, isStreaming, selectedDatasets, clearChat, sendMessage } =
    useChatStore();

  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleLogout = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  return (
    <div className="chat-layout">
      {/* Sidebar */}
      <aside className="chat-sidebar">
        <div className="sidebar-header">
          <h2>Gaia Chat</h2>
        </div>

        <DatasetSelector />

        <TopicExplorer onAskTopic={(query) => sendMessage(query)} />

        <DatasetManager />

        <div className="sidebar-actions">
          <button className="btn-secondary" onClick={clearChat}>
            New Chat
          </button>
          <button className="btn-ghost" onClick={handleLogout}>
            Logout
          </button>
        </div>
      </aside>

      {/* Main area */}
      <main className="chat-main">
        <div className="chat-messages">
          {messages.length === 0 && selectedDatasets.length === 0 && (
            <div className="chat-empty">
              <h3>Start a conversation</h3>
              <p>Select one or more datasets from the sidebar, then ask a question.</p>
            </div>
          )}

          {messages.length === 0 && selectedDatasets.length > 0 && (
            <TopicOverview onAsk={(query) => sendMessage(query)} />
          )}

          {messages.map((msg) => (
            <ChatMessage key={msg.id} message={msg} />
          ))}

          {isStreaming && (
            <div className="streaming-indicator">
              <span className="dot" />
              <span className="dot" />
              <span className="dot" />
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        <ChatInput disabled={isLoading || selectedDatasets.length === 0} />
      </main>
    </div>
  );
}
