import { useEffect, useState } from "react";
import { listDatasets, Dataset } from "../api/gaia";
import { useChatStore } from "../state/chatStore";

export default function DatasetSelector() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const { selectedDatasets, setSelectedDatasets } = useChatStore();

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    listDatasets()
      .then((ds) => {
        if (!cancelled) {
          setDatasets(ds);
          setError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  const filtered = datasets.filter((ds) =>
    ds.name.toLowerCase().includes(search.toLowerCase())
  );

  const toggle = (name: string) => {
    if (selectedDatasets.includes(name)) {
      setSelectedDatasets(selectedDatasets.filter((n) => n !== name));
    } else {
      setSelectedDatasets([...selectedDatasets, name]);
    }
  };

  const selectAll = () =>
    setSelectedDatasets(filtered.map((ds) => ds.name));

  const clearAll = () => setSelectedDatasets([]);

  return (
    <div className="dataset-selector">
      <div className="ds-header">
        <span className="ds-title">Datasets</span>
        {selectedDatasets.length > 0 && (
          <span className="ds-badge">{selectedDatasets.length} selected</span>
        )}
      </div>

      {/* Search */}
      <div className="ds-search-wrap">
        <input
          className="ds-search"
          type="text"
          placeholder="Search datasets…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {/* Bulk actions */}
      {!loading && filtered.length > 0 && (
        <div className="ds-actions">
          <button className="ds-action-btn" onClick={selectAll}>
            Select all
          </button>
          <button className="ds-action-btn" onClick={clearAll}>
            Clear
          </button>
        </div>
      )}

      {loading && <p className="ds-loading">Loading datasets…</p>}
      {error && <p className="ds-error">{error}</p>}
      {!loading && filtered.length === 0 && !error && (
        <p className="ds-empty">
          {search ? "No datasets match your search." : "No datasets found."}
        </p>
      )}

      <ul className="ds-list">
        {filtered.map((ds) => (
          <li key={ds.name}>
            <label className={`ds-item ${selectedDatasets.includes(ds.name) ? "ds-item--selected" : ""}`}>
              <input
                type="checkbox"
                checked={selectedDatasets.includes(ds.name)}
                onChange={() => toggle(ds.name)}
              />
              <span className="ds-name" title={ds.name}>{ds.name}</span>
            </label>
          </li>
        ))}
      </ul>
    </div>
  );
}
