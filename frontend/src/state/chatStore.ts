import { create } from "zustand";
import { ask, askStream, getDiscovery, type GaiaDocument, type TopicNode } from "../api/gaia";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  documents?: GaiaDocument[];
}

interface ChatState {
  messages: ChatMessage[];
  currentConversationId: string | null;
  isLoading: boolean;
  isStreaming: boolean;
  selectedDatasets: string[];
  // Topics (shared between sidebar TopicExplorer and main TopicOverview)
  topics: TopicNode[];
  topicsLoading: boolean;
  topicsError: string | null;
  setSelectedDatasets: (names: string[]) => void;
  fetchTopics: (datasetName: string) => Promise<void>;
  sendMessage: (query: string, streaming?: boolean) => Promise<void>;
  clearChat: () => void;
}

let messageCounter = 0;
function nextId(): string {
  return `msg-${Date.now()}-${++messageCounter}`;
}

function extractTopicsFromResponse(data: unknown): TopicNode[] {
  if (!data || typeof data !== "object") return [];
  const obj = data as Record<string, unknown>;
  for (const key of ["themes", "topics", "clusters", "categories", "nodes", "children", "data", "results", "items"]) {
    if (Array.isArray(obj[key]) && (obj[key] as unknown[]).length > 0) return obj[key] as TopicNode[];
  }
  if (Array.isArray(data) && data.length > 0) return data as TopicNode[];
  return [];
}

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  currentConversationId: null,
  isLoading: false,
  isStreaming: false,
  selectedDatasets: [],
  topics: [],
  topicsLoading: false,
  topicsError: null,

  setSelectedDatasets: (names) => {
    set({ selectedDatasets: names, topics: [], topicsError: null });
    if (names.length > 0) {
      get().fetchTopics(names[0]);
    }
  },

  fetchTopics: async (datasetName: string) => {
    set({ topicsLoading: true, topicsError: null, topics: [] });
    try {
      const data = await getDiscovery(datasetName, 2);
      const extracted = extractTopicsFromResponse(data);
      set({
        topics: extracted,
        topicsLoading: false,
        topicsError: extracted.length === 0 ? "No topics found for this dataset." : null,
      });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load topics";
      set({ topicsLoading: false, topicsError: msg, topics: [] });
    }
  },

  sendMessage: async (query: string, streaming = true) => {
    const { selectedDatasets, currentConversationId, messages } = get();
    if (!selectedDatasets.length) return;

    const userMsg: ChatMessage = { id: nextId(), role: "user", content: query };
    set({ messages: [...messages, userMsg], isLoading: true });

    const assistantId = nextId();
    const assistantMsg: ChatMessage = {
      id: assistantId,
      role: "assistant",
      content: "",
    };
    set((s) => ({ messages: [...s.messages, assistantMsg] }));

    if (streaming) {
      set({ isStreaming: true });
      try {
        await askStream(
          query,
          selectedDatasets,
          currentConversationId ?? undefined,
          (token) => {
            set((s) => ({
              messages: s.messages.map((m) =>
                m.id === assistantId ? { ...m, content: m.content + token } : m,
              ),
            }));
          },
          (_full, docs) => {
            set((s) => ({
              messages: s.messages.map((m) =>
                m.id === assistantId ? { ...m, documents: docs } : m,
              ),
              isStreaming: false,
              isLoading: false,
            }));
          },
        );
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : "Stream error";
        set((s) => ({
          messages: s.messages.map((m) =>
            m.id === assistantId
              ? { ...m, content: `**Error:** ${msg}` }
              : m,
          ),
          isStreaming: false,
          isLoading: false,
        }));
      }
    } else {
      try {
        const result = await ask(
          query,
          selectedDatasets,
          currentConversationId ?? undefined,
        );
        set((s) => ({
          messages: s.messages.map((m) =>
            m.id === assistantId
              ? { ...m, content: result.responseString, documents: result.documents ?? [] }
              : m,
          ),
          currentConversationId:
            result.conversationId ?? s.currentConversationId,
          isLoading: false,
        }));
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : "Request error";
        set((s) => ({
          messages: s.messages.map((m) =>
            m.id === assistantId
              ? { ...m, content: `**Error:** ${msg}` }
              : m,
          ),
          isLoading: false,
        }));
      }
    }
  },

  clearChat: () =>
    set({ messages: [], currentConversationId: null }),
}));
