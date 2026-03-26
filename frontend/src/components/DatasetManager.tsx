import { useEffect, useRef, useState } from "react";
import {
  createDataset,
  triggerIndexing,
  getDatasetDetails,
  type DatasetDetails,
  type IndexingStats,
} from "../api/gaia";

// ── Indexing Status Badge ─────────────────────────────────────────────────────

function statusColor(status?: string): string {
  switch (status?.toLowerCase()) {
    case "completed": return "var(--accent)";
    case "running":   return "#f59e0b";
    case "failed":    return "var(--danger)";
    default:          return "var(--text-muted)";
  }
}

function IndexingStatus({ stats, onClose }: { stats: IndexingStats | null; onClose: () => void }) {
  if (!stats) return null;
  const pct = stats.totalFiles
    ? Math.round(((stats.indexedFiles ?? 0) / stats.totalFiles) * 100)
    : null;

  return (
    <div className="dm-status-card">
      <div className="dm-status-header">
        <span className="dm-status-badge" style={{ color: statusColor(stats.status) }}>
          ● {stats.status ?? "Unknown"}
        </span>
        <button className="dm-close-btn" onClick={onClose}>✕</button>
      </div>
      {pct !== null && (
        <div className="dm-progress-bar">
          <div className="dm-progress-fill" style={{ width: `${pct}%` }} />
        </div>
      )}
      <div className="dm-status-grid">
        <span>Indexed</span><span>{stats.indexedFiles ?? "—"} / {stats.totalFiles ?? "—"} files</span>
        {(stats.failedFiles ?? 0) > 0 && (
          <><span className="dm-warn">Failed</span><span className="dm-warn">{stats.failedFiles}</span></>
        )}
        {stats.lastIndexedAt && (
          <><span>Last run</span><span>{new Date(stats.lastIndexedAt).toLocaleString()}</span></>
        )}
      </div>
    </div>
  );
}

// ── Create Dataset Form ────────────────────────────────────────────────────────

interface CreateFormProps {
  onCreated: (name: string) => void;
  onCancel: () => void;
}

function CreateDatasetForm({ onCreated, onCancel }: CreateFormProps) {
  const [name, setName]         = useState("");
  const [desc, setDesc]         = useState("");
  const [viewName, setViewName] = useState("");
  const [includePaths, setIncludePaths] = useState("");
  const [excludePaths, setExcludePaths] = useState("");
  const [extensions, setExtensions]     = useState(".pdf,.docx,.xlsx");
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || !viewName.trim()) return;
    setLoading(true);
    setError(null);
    try {
      await createDataset(name.trim(), desc.trim(), [
        {
          sourceType: "CohesityView",
          viewName: viewName.trim(),
          includePaths: includePaths ? includePaths.split(",").map(p => p.trim()) : undefined,
          excludePaths: excludePaths ? excludePaths.split(",").map(p => p.trim()) : undefined,
          fileFilters: {
            includeExtensions: extensions ? extensions.split(",").map(e => e.trim()) : undefined,
          },
        },
      ]);
      onCreated(name.trim());
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to create dataset");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form className="dm-form" onSubmit={handleSubmit}>
      <h4 className="dm-form-title">New Dataset</h4>

      <label className="dm-label">Dataset name *</label>
      <input className="dm-input" placeholder="e.g. engineering-docs" value={name}
        onChange={e => setName(e.target.value)} required />

      <label className="dm-label">Description</label>
      <input className="dm-input" placeholder="Optional description" value={desc}
        onChange={e => setDesc(e.target.value)} />

      <label className="dm-label">Cohesity View name *</label>
      <input className="dm-input" placeholder="e.g. eng-wiki" value={viewName}
        onChange={e => setViewName(e.target.value)} required />

      <label className="dm-label">Include paths (comma-separated)</label>
      <input className="dm-input" placeholder="/design-docs, /runbooks" value={includePaths}
        onChange={e => setIncludePaths(e.target.value)} />

      <label className="dm-label">Exclude paths (comma-separated)</label>
      <input className="dm-input" placeholder="/archive, /temp" value={excludePaths}
        onChange={e => setExcludePaths(e.target.value)} />

      <label className="dm-label">File extensions</label>
      <input className="dm-input" placeholder=".pdf, .docx, .xlsx" value={extensions}
        onChange={e => setExtensions(e.target.value)} />

      {error && <p className="dm-error">{error}</p>}

      <div className="dm-form-actions">
        <button type="submit" className="dm-btn-primary" disabled={loading}>
          {loading ? "Creating…" : "Create Dataset"}
        </button>
        <button type="button" className="dm-btn-ghost" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

// ── Indexing Panel ─────────────────────────────────────────────────────────────

interface IndexingPanelProps {
  datasetName: string;
  onClose: () => void;
}

function IndexingPanel({ datasetName, onClose }: IndexingPanelProps) {
  const [details, setDetails]   = useState<DatasetDetails | null>(null);
  const [triggering, setTriggering] = useState(false);
  const [error, setError]       = useState<string | null>(null);
  const [polling, setPolling]   = useState(false);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  async function fetchDetails() {
    try {
      const d = await getDatasetDetails(datasetName);
      setDetails(d);
      const status = d.indexingStats?.status?.toLowerCase();
      if (status === "completed" || status === "failed") {
        stopPolling();
      }
    } catch {
      // ignore transient errors
    }
  }

  function startPolling() {
    setPolling(true);
    fetchDetails();
    pollingRef.current = setInterval(fetchDetails, 5000);
  }

  function stopPolling() {
    setPolling(false);
    if (pollingRef.current) clearInterval(pollingRef.current);
  }

  useEffect(() => {
    fetchDetails();
    return () => stopPolling();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datasetName]);

  async function handleTrigger() {
    setTriggering(true);
    setError(null);
    try {
      await triggerIndexing(datasetName);
      startPolling();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to trigger indexing");
    } finally {
      setTriggering(false);
    }
  }

  return (
    <div className="dm-indexing-panel">
      <div className="dm-panel-header">
        <span className="dm-panel-title">{datasetName}</span>
        <button className="dm-close-btn" onClick={onClose}>✕</button>
      </div>

      <IndexingStatus
        stats={details?.indexingStats ?? null}
        onClose={() => {}}
      />

      {polling && (
        <p className="dm-polling-msg">Polling every 5s…</p>
      )}

      {error && <p className="dm-error">{error}</p>}

      <div className="dm-panel-actions">
        <button className="dm-btn-primary" onClick={handleTrigger} disabled={triggering || polling}>
          {triggering ? "Triggering…" : "▶ Trigger Indexing"}
        </button>
        {polling && (
          <button className="dm-btn-ghost" onClick={stopPolling}>Stop polling</button>
        )}
        {!polling && details?.indexingStats && (
          <button className="dm-btn-ghost" onClick={startPolling}>↻ Refresh</button>
        )}
      </div>
    </div>
  );
}

// ── Main DatasetManager ────────────────────────────────────────────────────────

export default function DatasetManager() {
  const [open, setOpen]             = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [indexingDataset, setIndexingDataset] = useState<string | null>(null);
  const [lastCreated, setLastCreated] = useState<string | null>(null);

  function handleCreated(name: string) {
    setLastCreated(name);
    setShowCreate(false);
    setIndexingDataset(name);
  }

  return (
    <div className="dataset-manager">
      <div className="dm-header" onClick={() => setOpen(o => !o)}>
        <span className="dm-title">Dataset Manager</span>
        <span className="dm-toggle">{open ? "▾" : "▸"}</span>
      </div>

      {open && (
        <div className="dm-body">
          {!showCreate && !indexingDataset && (
            <div className="dm-actions">
              <button className="dm-btn-primary" onClick={() => setShowCreate(true)}>
                + New Dataset
              </button>
              {lastCreated && (
                <button className="dm-btn-ghost" onClick={() => setIndexingDataset(lastCreated)}>
                  Index "{lastCreated}"
                </button>
              )}
            </div>
          )}

          {showCreate && (
            <CreateDatasetForm
              onCreated={handleCreated}
              onCancel={() => setShowCreate(false)}
            />
          )}

          {indexingDataset && (
            <IndexingPanel
              datasetName={indexingDataset}
              onClose={() => setIndexingDataset(null)}
            />
          )}
        </div>
      )}
    </div>
  );
}
