/**
 * „Einstellungen": the team's two editable values, each in its own card with its own „Speichern"
 * and „Auf Standard zurücksetzen": the agent's settings and the question catalog. Changes apply
 * from the next conversation, because every conversation copies both when it starts.
 */
import { InfoButton } from "../../layout/InfoButton";
import { AgentSettingsCard } from "./AgentSettingsCard";
import { CatalogCard } from "./CatalogCard";

export function SettingsPage() {
  return (
    <>
      <div className="page-head with-info">
        <h1>Einstellungen</h1>
        <InfoButton label="Einstellungen">
          Änderungen gelten ab dem nächsten Gespräch. Laufende und vergangene Gespräche behalten ihre
          Einstellungen und Fragen.
        </InfoButton>
      </div>
      <AgentSettingsCard />
      <CatalogCard />
    </>
  );
}
