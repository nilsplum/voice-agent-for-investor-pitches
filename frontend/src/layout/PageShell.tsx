/**
 * The page shell around every page (the layout route in App.tsx): a header with the app's name and,
 * for a logged-in user, the area as a small pill below it, the team's navigation, the user's name and
 * „Abmelden" (on phone width the navigation gets its own line and the name is hidden). The shell is
 * exactly as high as the screen: the header stays in view, and `main` below it is the page's one
 * scroll area (the scroll model in styles/base.css). The page itself is centered with a readable
 * width, wider in the team area (tables, conversation details), and works down to phone width.
 *
 * „Abmelden" loads the app afresh at the welcome page (like the API client's 401 handling), so no
 * state of the old login survives, and the route guards never see a half-finished logout.
 * While a founder's call runs (`callActive`), the header offers no way out: no links and no
 * „Abmelden", because STOPP is how a conversation ends. It offers the mute button instead, which
 * sets the app-wide `muted` (the call silences its microphone, call/useCall.ts).
 */
import { LogOut, Mic, MicOff } from "lucide-react";
import { Link, NavLink, Outlet } from "react-router";
import { api, errorMessage } from "../api/client";
import { useApp } from "../AppProvider";
import { ROLE_AREAS } from "../labels";
import { useNotify } from "../notifications/NotificationsProvider";

const TEAM_NAVIGATION = [
  { to: "/team/conversations", label: "Gespräche" },
  { to: "/team/access-codes", label: "Zugangscodes" },
  { to: "/team/settings", label: "Einstellungen" },
];

export function PageShell() {
  const { me, callActive, muted, setMuted } = useApp();
  const notify = useNotify();

  async function logOut() {
    try {
      await api.logout();
      window.location.assign("/");
    } catch (error) {
      notify(errorMessage(error), "error");
    }
  }

  return (
    <div className="shell">
      <header className="header">
        <div className="brand-block">
          {callActive ? (
            <span className="brand">Voice Agent for Investor Pitches</span>
          ) : (
            <Link to="/" className="brand">Voice Agent for Investor Pitches</Link>
          )}
          {me && <span className="label-pill">{ROLE_AREAS[me.role]}</span>}
        </div>
        {me?.role === "team" && (
          <nav className="nav">
            {TEAM_NAVIGATION.map((item) => (
              <NavLink key={item.to} to={item.to}>{item.label}</NavLink>
            ))}
          </nav>
        )}
        {me && (
          <div className="header-end">
            {callActive && (
              <button
                type="button"
                className={muted ? "button button-small button-muted" : "button button-small"}
                aria-pressed={muted}
                onClick={() => setMuted(!muted)}
              >
                {muted ? <MicOff size={16} aria-hidden /> : <Mic size={16} aria-hidden />}
                {muted ? "Stumm" : "Stummschalten"}
              </button>
            )}
            <span className="user">{me.name}</span>
            {!callActive && (
              <button className="button button-small" onClick={logOut}>
                <LogOut size={16} aria-hidden /> Abmelden
              </button>
            )}
          </div>
        )}
      </header>
      <main className="main">
        <div className={me?.role === "team" ? "content content-wide" : "content"}>
          <Outlet />
        </div>
      </main>
    </div>
  );
}
