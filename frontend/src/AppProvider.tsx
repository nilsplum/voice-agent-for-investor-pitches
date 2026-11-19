/**
 * App-wide state: the backend's config values and who is logged in, loaded once when the app
 * starts, and the state of a founder's running call. Pages read them with `useApp()`. Signup and
 * login update `me` with `setMe`, and the route guards in App.tsx follow it; logging out reloads the
 * app instead (layout/PageShell.tsx). The call (call/useCall.ts) sets `callActive`, which hides the
 * header's links while it runs, so STOPP is the only way out of a conversation, and shows the
 * header's mute button instead. `muted` is set by that button and read by the call, which silences
 * the microphone it sends; the call resets it when it ends.
 * START_PAGES is the one definition of each role's start page.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, errorMessage, type AppConfig, type Me } from "./api/client";

export const START_PAGES: Record<Me["role"], string> = {
  founder: "/conversations",
  team: "/team/conversations",
};

type AppState = {
  appConfig: AppConfig;
  me: Me | null;
  setMe: (me: Me | null) => void;
  callActive: boolean;
  setCallActive: (active: boolean) => void;
  muted: boolean;
  setMuted: (muted: boolean) => void;
};

const AppContext = createContext<AppState | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [loaded, setLoaded] = useState<{ appConfig: AppConfig; me: Me | null } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [callActive, setCallActive] = useState(false);
  const [muted, setMuted] = useState(false);

  const load = useCallback(() => {
    setError(null);
    Promise.all([api.appConfig(), api.me()]).then(
      ([appConfig, me]) => setLoaded({ appConfig, me }),
      (failure: unknown) => setError(errorMessage(failure)),
    );
  }, []);
  useEffect(load, [load]);

  const state = useMemo<AppState | null>(
    () =>
      loaded && {
        ...loaded,
        setMe: (me) => setLoaded((current) => current && { ...current, me }),
        callActive,
        setCallActive,
        muted,
        setMuted,
      },
    [loaded, callActive, muted],
  );

  if (error) {
    return (
      <div className="page-center">
        <p className="error">{error}</p>
        <button className="button" onClick={load}>Erneut versuchen</button>
      </div>
    );
  }
  if (!state) return null; // the first load takes a moment; nothing is shown until it is done
  return <AppContext.Provider value={state}>{children}</AppContext.Provider>;
}

export function useApp(): AppState {
  const state = useContext(AppContext);
  if (!state) throw new Error("useApp() needs the AppProvider around it");
  return state;
}
