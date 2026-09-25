import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { LockIcon, MailIcon, ShieldIcon } from "../components/Icons";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState("login");
  const [error, setError] = useState(null);
  const { login, register } = useAuth();
  const navigate = useNavigate();

  async function handleSubmit(event) {
    event.preventDefault();
    setError(null);
    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        await register(email, password);
      }
      navigate("/");
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="auth-page">
      <form onSubmit={handleSubmit} className="auth-form">
        <span className="auth-badge">
          <ShieldIcon />
        </span>
        <span className="welcome-kicker">Applied Economics &amp; Data Science</span>
        <h1>{mode === "login" ? "Admin Login" : "Create Admin Account"}</h1>
        <p className="auth-subtitle">
          This area is only for admins managing content and user contributions.
          You don't need to log in to use the chat.
        </p>
        <div className="input-with-icon">
          <MailIcon />
          <input
            type="email"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </div>
        <div className="input-with-icon">
          <LockIcon />
          <input
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </div>
        {error && <p className="error">{error}</p>}
        <button type="submit">{mode === "login" ? "Log in" : "Create account"}</button>
        <button
          type="button"
          className="link-button"
          onClick={() => setMode(mode === "login" ? "register" : "login")}
        >
          {mode === "login" ? "Don't have an account? Create one" : "Already have an account? Log in"}
        </button>
      </form>
    </div>
  );
}
