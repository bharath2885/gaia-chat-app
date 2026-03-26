import { useState } from "react";
import { useChatStore } from "../state/chatStore";
import type { TopicNode } from "../api/gaia";

function topicLabel(t: TopicNode): string {
  return t.name ?? t.label ?? t.title ?? "Unnamed topic";
}

function topicChildren(t: TopicNode): TopicNode[] {
  return t.subThemes ?? t.children ?? t.subtopics ?? t.topics ?? t.themes ?? [];
}

function TopicRow({
  topic,
  depth,
  onAsk,
}: {
  topic: TopicNode;
  depth: number;
  onAsk: (label: string) => void;
}) {
  const children = topicChildren(topic);
  const [open, setOpen] = useState(depth === 0);
  const label = topicLabel(topic);
  const questions = topic.suggestedQuestions ?? [];

  return (
    <li className="te-row" style={{ paddingLeft: `${depth * 12}px` }}>
      <div className="te-row-header">
        {children.length > 0 ? (
          <button
            className="te-chevron"
            onClick={() => setOpen((o) => !o)}
            aria-label={open ? "Collapse" : "Expand"}
          >
            {open ? "▾" : "▸"}
          </button>
        ) : (
          <span className="te-chevron-spacer" />
        )}
        <span className="te-label" title={topic.description ?? topic.summary ?? label}>
          {label}
          {topic.percentage !== undefined && (
            <span className="te-count">{topic.percentage.toFixed(0)}%</span>
          )}
          {topic.count !== undefined && topic.percentage === undefined && (
            <span className="te-count">{topic.count}</span>
          )}
        </span>
        <button
          className="te-ask-btn"
          title={`Ask about "${label}"`}
          onClick={() => onAsk(label)}
        >
          Ask →
        </button>
      </div>

      {open && questions.length > 0 && (
        <ul className="te-questions">
          {questions.map((q, i) => (
            <li key={i}>
              <button className="te-question-chip" onClick={() => onAsk(q)}>
                {q}
              </button>
            </li>
          ))}
        </ul>
      )}

      {open && children.length > 0 && (
        <ul className="te-children">
          {children.map((child, i) => (
            <TopicRow
              key={topicLabel(child) + i}
              topic={child}
              depth={depth + 1}
              onAsk={onAsk}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

interface Props {
  onAskTopic: (query: string) => void;
}

export default function TopicExplorer({ onAskTopic }: Props) {
  const selectedDatasets = useChatStore((s) => s.selectedDatasets);
  const topics = useChatStore((s) => s.topics);
  const topicsLoading = useChatStore((s) => s.topicsLoading);
  const topicsError = useChatStore((s) => s.topicsError);
  const fetchTopics = useChatStore((s) => s.fetchTopics);
  const activeDataset = selectedDatasets[0] ?? null;

  const [collapsed, setCollapsed] = useState(false);

  if (!activeDataset) return null;

  return (
    <div className="topic-explorer">
      <div className="te-header" onClick={() => setCollapsed((c) => !c)}>
        <span className="te-title">Topic Explorer</span>
        <span className="te-toggle">{collapsed ? "▸" : "▾"}</span>
      </div>

      {!collapsed && (
        <div className="te-body">
          {topicsLoading && <p className="te-status">Loading topics…</p>}

          {topicsError && !topicsLoading && (
            <div className="te-error">
              <p>{topicsError}</p>
              <button className="te-retry-btn" onClick={() => fetchTopics(activeDataset)}>
                Retry
              </button>
            </div>
          )}

          {!topicsLoading && !topicsError && topics.length > 0 && (
            <ul className="te-list">
              {topics.map((t, i) => (
                <TopicRow
                  key={topicLabel(t) + i}
                  topic={t}
                  depth={0}
                  onAsk={(label) =>
                    onAskTopic(`Tell me about "${label}" in the context of ${activeDataset}`)
                  }
                />
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
