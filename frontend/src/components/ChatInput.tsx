import { FormEvent, useState } from "react";
import { useChatStore } from "../state/chatStore";

interface Props {
  disabled?: boolean;
}

export default function ChatInput({ disabled = false }: Props) {
  const [text, setText] = useState("");
  const sendMessage = useChatStore((s) => s.sendMessage);
  const isStreaming = useChatStore((s) => s.isStreaming);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const trimmed = text.trim();
    if (!trimmed || disabled || isStreaming) return;
    setText("");
    sendMessage(trimmed);
  };

  return (
    <form className="chat-input-bar" onSubmit={handleSubmit}>
      <input
        type="text"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={
          disabled
            ? "Select a dataset to start chatting…"
            : "Ask a question about your data…"
        }
        disabled={disabled || isStreaming}
        autoFocus
      />
      <button type="submit" disabled={disabled || isStreaming || !text.trim()}>
        {isStreaming ? "Streaming…" : "Send"}
      </button>
    </form>
  );
}
