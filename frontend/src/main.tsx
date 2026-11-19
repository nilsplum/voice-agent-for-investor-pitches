/**
 * Entry point: mounts the app with its providers (router, notifications, app state) and the styles.
 * Every page, the page shell included, sits inside all three providers.
 */
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
import { App } from "./App";
import { AppProvider } from "./AppProvider";
import { NotificationsProvider } from "./notifications/NotificationsProvider";
import "./styles/tokens.css";
import "./styles/base.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <NotificationsProvider>
        <AppProvider>
          <App />
        </AppProvider>
      </NotificationsProvider>
    </BrowserRouter>
  </StrictMode>,
);
