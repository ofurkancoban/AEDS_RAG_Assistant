import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { LogoutIcon, ShieldIcon } from "./Icons";
import ThemeToggle from "./ThemeToggle";

export default function TopUtility() {
  const { isAuthenticated, isAdmin, logout } = useAuth();
  const navigate = useNavigate();

  function handleLogout() {
    logout();
    navigate("/");
  }

  return (
    <>
      {!isAuthenticated && (
        // Intentionally invisible: admin entry point with no visual affordance.
        <Link to="/login" className="hidden-admin-entry" aria-label="Admin login" tabIndex={0} />
      )}
      <div className="top-utility">
        <ThemeToggle />
        {isAuthenticated && isAdmin && (
          <Link to="/admin" className="top-utility-link">
            <ShieldIcon /> Admin
          </Link>
        )}
        {isAuthenticated && (
          <button type="button" className="top-utility-link" onClick={handleLogout}>
            <LogoutIcon /> Log out
          </button>
        )}
      </div>
    </>
  );
}
