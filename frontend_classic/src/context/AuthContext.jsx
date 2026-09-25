import { createContext, useContext, useMemo, useState } from "react";
import { login as apiLogin, register as apiRegister } from "../api/client";

const AuthContext = createContext(null);

function decodeRole(token) {
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    return payload.role;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem("access_token"));

  const role = useMemo(() => (token ? decodeRole(token) : null), [token]);

  async function login(email, password) {
    const { access_token } = await apiLogin(email, password);
    localStorage.setItem("access_token", access_token);
    setToken(access_token);
  }

  async function register(email, password) {
    const { access_token } = await apiRegister(email, password);
    localStorage.setItem("access_token", access_token);
    setToken(access_token);
  }

  function logout() {
    localStorage.removeItem("access_token");
    setToken(null);
  }

  const value = { token, role, isAuthenticated: Boolean(token), isAdmin: role === "admin", login, register, logout };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider");
  return context;
}
