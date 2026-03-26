import { apiFetch, API_URL, buildHeaders } from "./client";

export interface LoginResult {
  sessionId: string;
}

export interface GaiaDocument {
  // Actual field names returned by the Gaia API
  documentId?: string;
  name?: string;
  absolutePath?: string;
  downloadUrl?: string | null;
  type?: string;
  uid?: string;
  citations?: Array<{ cosineScore?: number; textSnippet?: string }>;
  objectInfo?: Record<string, unknown>;
}

export interface AskResult {
  responseString: string;
  queryUid: string;
  conversationId?: string;
  documents?: GaiaDocument[];
}

export interface Dataset {
  name: string;
  datasetId?: string;
  description?: string;
}

export interface Conversation {
  conversationId: string;
  title?: string;
  createdAt?: string;
}

export async function login(apiKey: string): Promise<LoginResult> {
  return apiFetch<LoginResult>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ apiKey }),
  });
}

export async function logout(): Promise<void> {
  await apiFetch("/auth/logout", { method: "POST" });
}

export async function listDatasets(): Promise<Dataset[]> {
  const data = await apiFetch<{ datasets?: Dataset[] }>("/datasets");
  return data.datasets ?? [];
}

export interface DataSource {
  sourceType: string;
  viewName?: string;
  includePaths?: string[];
  excludePaths?: string[];
  fileFilters?: {
    includeExtensions?: string[];
    excludeExtensions?: string[];
    maxFileSizeMB?: number;
  };
}

export interface IndexingStats {
  status?: string;
  totalFiles?: number;
  indexedFiles?: number;
  failedFiles?: number;
  indexSizeBytes?: number;
  lastIndexedAt?: string;
}

export interface DatasetDetails {
  name: string;
  status?: string;
  description?: string;
  objectCount?: number;
  indexingStats?: IndexingStats;
}

export async function createDataset(
  name: string,
  description: string,
  dataSources: DataSource[],
): Promise<unknown> {
  return apiFetch("/datasets", {
    method: "POST",
    body: JSON.stringify({ name, description, dataSources }),
  });
}

export async function triggerIndexing(datasetName: string): Promise<unknown> {
  return apiFetch(`/datasets/${encodeURIComponent(datasetName)}/index`, {
    method: "POST",
  });
}

export async function getDatasetDetails(datasetName: string): Promise<DatasetDetails> {
  return apiFetch(`/datasets/${encodeURIComponent(datasetName)}/details`);
}

export async function ask(
  query: string,
  datasetNames: string[],
  conversationId?: string,
): Promise<AskResult> {
  return apiFetch<AskResult>("/ask", {
    method: "POST",
    body: JSON.stringify({ query, datasetNames, conversationId }),
  });
}

export async function askStream(
  query: string,
  datasetNames: string[],
  conversationId?: string,
  onChunk: (text: string) => void = () => {},
  onDone: (full: string, docs: GaiaDocument[]) => void = () => {},
): Promise<void> {
  const resp = await fetch(`${API_URL}/ask/stream`, {
    method: "POST",
    headers: buildHeaders(),
    body: JSON.stringify({ query, datasetNames, conversationId }),
  });

  if (!resp.ok) {
    const body = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(body.detail ?? `Stream request failed: ${resp.status}`);
  }

  const reader = resp.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let accumulated = "";
  let fullText = "";
  const allDocuments: GaiaDocument[] = [];
  const seenDocIds = new Set<string>();

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    accumulated += decoder.decode(value, { stream: true });
    const lines = accumulated.split("\n");
    accumulated = lines.pop() ?? "";

    for (const line of lines) {
      if (line.startsWith("data: ")) {
        const payload = line.slice(6);
        if (payload === "[DONE]" || payload === "[ERROR]") continue;

        try {
          const parsed = JSON.parse(payload);
          const token =
            parsed.data?.responseString ??
            parsed.responseString ??
            parsed.token ??
            parsed.delta?.content ??
            parsed.choices?.[0]?.delta?.content ??
            "";
          if (token) {
            fullText += token;
            onChunk(token);
          }

          // Collect documents, deduplicating by docId or filename
          const docs: GaiaDocument[] = parsed.data?.documents ?? parsed.documents ?? [];
          for (const doc of docs) {
            const key = doc.documentId ?? doc.uid ?? doc.name ?? JSON.stringify(doc);
            if (!seenDocIds.has(key)) {
              seenDocIds.add(key);
              allDocuments.push(doc);
            }
          }
        } catch {
          if (payload.trim()) {
            fullText += payload;
            onChunk(payload);
          }
        }
      }
    }
  }

  onDone(fullText, allDocuments);
}

export interface TopicNode {
  // Real Gaia API fields (from GET /dataset/{id}/discovery)
  name?: string;
  uuid?: string;
  percentage?: number;
  subThemes?: TopicNode[];
  suggestedQuestions?: string[];
  // Generic fallbacks for other possible shapes
  label?: string;
  title?: string;
  description?: string;
  summary?: string;
  count?: number;
  children?: TopicNode[];
  subtopics?: TopicNode[];
  topics?: TopicNode[];
  themes?: TopicNode[];
}

export async function getDiscovery(
  datasetName: string,
  level = 2,
): Promise<unknown> {
  return apiFetch(`/datasets/${encodeURIComponent(datasetName)}/discovery?num_levels=${level}`);
}

export async function getThemeSummary(
  datasetName: string,
  themeUuid: string,
): Promise<string> {
  const data = await apiFetch<{ summary?: string } | string>(
    `/datasets/${encodeURIComponent(datasetName)}/themes/${themeUuid}/summary`,
  );
  if (typeof data === "string") return data;
  return (data as { summary?: string }).summary ?? "";
}

export async function getThemeQuestions(
  datasetName: string,
  themeUuid: string,
): Promise<string[]> {
  const data = await apiFetch<string[] | { questions?: string[] }>(
    `/datasets/${encodeURIComponent(datasetName)}/themes/${themeUuid}/questions`,
  );
  if (Array.isArray(data)) return data;
  return (data as { questions?: string[] }).questions ?? [];
}

export async function listConversations(): Promise<Conversation[]> {
  const data = await apiFetch<{ conversations?: Conversation[] }>(
    "/conversations",
  );
  return data.conversations ?? [];
}

export async function getHistory(
  conversationId: string,
): Promise<{ messages: unknown[] }> {
  return apiFetch(`/conversations/${conversationId}/history`);
}
