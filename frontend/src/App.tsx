import { Navigate, Route, Routes } from "react-router-dom";
import { useSessionStore } from "./state/sessionStore";
import LoginPage from "./pages/LoginPage";
import ChatPage from "./pages/ChatPage";

export default function App() {
  const isAuthenticated = useSessionStore((s) => s.isAuthenticated);

  return (
    <Routes>
      <Route
        path="/"
        element={
          <Navigate to={isAuthenticated ? "/chat" : "/login"} replace />
        }
      />
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/chat"
        element={isAuthenticated ? <ChatPage /> : <Navigate to="/login" replace />}
      />
    </Routes>
  );
}
