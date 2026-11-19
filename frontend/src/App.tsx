/**
 * The router: every page inside the one page shell, and the guards that decide who sees which page.
 * Founder pages need the founder role, team pages the team role (without a login: the login page;
 * with the other role: that role's start page). Guest pages (welcome, signup, login) send a
 * logged-in user to their start page, which is also how login lands there once it sets the user
 * (signup goes into the new conversation instead).
 */
import type { ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router";
import type { Me } from "./api/client";
import { START_PAGES, useApp } from "./AppProvider";
import { PageShell } from "./layout/PageShell";
import { ConversationPage } from "./pages/founder/ConversationPage";
import { ConversationsPage } from "./pages/founder/ConversationsPage";
import { Login } from "./pages/Login";
import { NotFound } from "./pages/NotFound";
import { Signup } from "./pages/Signup";
import { AccessCodesPage } from "./pages/team/AccessCodesPage";
import { ConversationDetailPage } from "./pages/team/ConversationDetailPage";
import { ConversationsPage as TeamConversationsPage } from "./pages/team/ConversationsPage";
import { SettingsPage } from "./pages/team/SettingsPage";
import { Welcome } from "./pages/Welcome";

export function App() {
  return (
    <Routes>
      <Route element={<PageShell />}>
        <Route path="/" element={<GuestOnly><Welcome /></GuestOnly>} />
        <Route path="/signup" element={<GuestOnly><Signup /></GuestOnly>} />
        <Route path="/login" element={<GuestOnly><Login /></GuestOnly>} />
        <Route path="/conversations" element={<RequireRole role="founder"><ConversationsPage /></RequireRole>} />
        <Route path="/conversations/:id" element={<RequireRole role="founder"><ConversationPage /></RequireRole>} />
        <Route path="/team/conversations" element={<RequireRole role="team"><TeamConversationsPage /></RequireRole>} />
        <Route path="/team/conversations/:id" element={<RequireRole role="team"><ConversationDetailPage /></RequireRole>} />
        <Route path="/team/access-codes" element={<RequireRole role="team"><AccessCodesPage /></RequireRole>} />
        <Route path="/team/settings" element={<RequireRole role="team"><SettingsPage /></RequireRole>} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}

function RequireRole({ role, children }: { role: Me["role"]; children: ReactNode }) {
  const { me } = useApp();
  if (!me) return <Navigate to="/login" replace />;
  if (me.role !== role) return <Navigate to={START_PAGES[me.role]} replace />;
  return children;
}

function GuestOnly({ children }: { children: ReactNode }) {
  const { me } = useApp();
  return me ? <Navigate to={START_PAGES[me.role]} replace /> : children;
}
