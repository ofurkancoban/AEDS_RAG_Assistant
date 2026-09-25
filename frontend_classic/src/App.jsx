import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./context/AuthContext";
import AdminPage from "./pages/AdminPage";
import ChatPage from "./pages/ChatPage";
import LoginPage from "./pages/LoginPage";
import TopUtility from "./components/TopUtility";
import FloatingBackground from "./components/FloatingBackground";

function RequireAdmin({ children }) {
  const { isAdmin } = useAuth();
  return isAdmin ? children : <Navigate to="/" replace />;
}

export default function App() {
  return (
    <div className="app-shell">
      <div className="bg-decoration" aria-hidden="true">
        <span className="bg-blob bg-blob-1" />
        <span className="bg-blob bg-blob-2" />
        <FloatingBackground />
      </div>
      <TopUtility />
      <main className="main-area">
        <Routes>
          <Route path="/" element={<ChatPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route
            path="/admin"
            element={
              <RequireAdmin>
                <AdminPage />
              </RequireAdmin>
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
