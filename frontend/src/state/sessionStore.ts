import { create } from "zustand";
import { login as apiLogin, logout as apiLogout } from "../api/gaia";

interface SessionState {
  sessionId: string | null;
  isAuthenticated: boolean;
  error: string | null;
  loading: boolean;
  login: (apiKey: string) => Promise<void>;
  logout: () => Promise<void>;
  hydrate: () => void;
}

export const useSessionStore = create<SessionState>((set) => ({
  sessionId: null,
  isAuthenticated: false,
  error: null,
  loading: false,

  hydrate: () => {
    const sid = sessionStorage.getItem("sessionId");
    if (sid) {
      set({ sessionId: sid, isAuthenticated: true });
    }
  },

  login: async (apiKey: string) => {
    set({ loading: true, error: null });
    try {
      const { sessionId } = await apiLogin(apiKey);
      sessionStorage.setItem("sessionId", sessionId);
      set({ sessionId, isAuthenticated: true, loading: false });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Login failed";
      set({ error: msg, loading: false });
    }
  },

  logout: async () => {
    try {
      await apiLogout();
    } catch {
      // best effort
    }
    sessionStorage.removeItem("sessionId");
    set({ sessionId: null, isAuthenticated: false });
  },
}));

// Rehydrate on module load
useSessionStore.getState().hydrate();
