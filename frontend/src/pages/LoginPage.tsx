import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useSessionStore } from "../state/sessionStore";

export default function LoginPage() {
  const [apiKey, setApiKey] = useState("");
  const { login, loading, error, isAuthenticated } = useSessionStore();
  const navigate = useNavigate();

  if (isAuthenticated) {
    navigate("/chat", { replace: true });
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    await login(apiKey);
    if (useSessionStore.getState().isAuthenticated) {
      navigate("/chat", { replace: true });
    }
  };

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-header">
          <h1>Gaia Chat</h1>
          <p className="login-subtitle">
            Enter your Helios API key to start chatting with your data.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="login-form">
          <label htmlFor="apiKey">API Key</label>
          <input
            id="apiKey"
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
            required
            autoFocus
          />

          {error && <p className="login-error">{error}</p>}

          <button type="submit" disabled={loading || !apiKey.trim()}>
            {loading ? "Authenticating…" : "Connect"}
          </button>
        </form>

        <p className="login-footnote">
          Your API key is sent to the backend for validation against
          Gaia and stored in an in-memory session. It is never persisted
          to disk.
        </p>
      </div>
    </div>
  );
}
