import { useChatStore } from "../state/chatStore";
import type { TopicNode } from "../api/gaia";

function topicLabel(t: TopicNode): string {
  return t.name ?? t.label ?? t.title ?? "Unnamed topic";
}

function topicChildren(t: TopicNode): TopicNode[] {
  return t.subThemes ?? t.children ?? t.subtopics ?? t.topics ?? t.themes ?? [];
}

interface Props {
  onAsk: (query: string) => void;
}

export default function TopicOverview({ onAsk }: Props) {
  const selectedDatasets = useChatStore((s) => s.selectedDatasets);
  const topics = useChatStore((s) => s.topics);
  const topicsLoading = useChatStore((s) => s.topicsLoading);
  const topicsError = useChatStore((s) => s.topicsError);
  const fetchTopics = useChatStore((s) => s.fetchTopics);
  const activeDataset = selectedDatasets[0] ?? null;

  if (!activeDataset) return null;

  if (topicsLoading) {
    return (
      <div className="topic-overview">
        <div className="tov-header">
          <span className="tov-icon">🔍</span>
          <div>
            <h3 className="tov-title">Exploring topics in <em>{activeDataset}</em></h3>
            <p className="tov-subtitle">Analysing dataset content…</p>
          </div>
        </div>
        <div className="tov-loading">
          <span className="dot" /><span className="dot" /><span className="dot" />
        </div>
      </div>
    );
  }

  if (topicsError) {
    return (
      <div className="topic-overview topic-overview--error">
        <div className="tov-header">
          <span className="tov-icon">📂</span>
          <div>
            <h3 className="tov-title">{activeDataset}</h3>
            <p className="tov-subtitle">Topic Explorer unavailable — ask a question to get started.</p>
          </div>
          <button className="tov-retry" onClick={() => fetchTopics(activeDataset)}>Retry</button>
        </div>
      </div>
    );
  }

  if (topics.length === 0) return null;

  return (
    <div className="topic-overview">
      <div className="tov-header">
        <span className="tov-icon">🗂️</span>
        <div>
          <h3 className="tov-title">Topics in <em>{activeDataset}</em></h3>
          <p className="tov-subtitle">
            Click a theme to explore it, or ask your own question below.
          </p>
        </div>
      </div>

      <div className="tov-grid">
        {topics.map((theme, i) => {
          const label = topicLabel(theme);
          const children = topicChildren(theme);
          const questions = theme.suggestedQuestions ?? [];
          const pct = theme.percentage;

          return (
            <div key={label + i} className="tov-card">
              <div className="tov-card-header">
                <span className="tov-card-name">{label}</span>
                {pct !== undefined && (
                  <span className="tov-card-pct">{pct.toFixed(0)}%</span>
                )}
              </div>

              {pct !== undefined && (
                <div className="tov-bar">
                  <div className="tov-bar-fill" style={{ width: `${Math.min(pct, 100)}%` }} />
                </div>
              )}

              {children.length > 0 && (
                <div className="tov-subthemes">
                  {children.slice(0, 3).map((child, j) => (
                    <button
                      key={j}
                      className="tov-subtheme-chip"
                      onClick={() => onAsk(`Tell me about "${topicLabel(child)}" in ${activeDataset}`)}
                    >
                      {topicLabel(child)}
                    </button>
                  ))}
                  {children.length > 3 && (
                    <span className="tov-subtheme-more">+{children.length - 3} more</span>
                  )}
                </div>
              )}

              {questions.length > 0 && (
                <div className="tov-questions">
                  {questions.slice(0, 2).map((q, j) => (
                    <button key={j} className="tov-question-chip" onClick={() => onAsk(q)}>
                      {q}
                    </button>
                  ))}
                </div>
              )}

              <button
                className="tov-ask-btn"
                onClick={() => onAsk(`Tell me about "${label}" in the context of ${activeDataset}`)}
              >
                Ask about this →
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
