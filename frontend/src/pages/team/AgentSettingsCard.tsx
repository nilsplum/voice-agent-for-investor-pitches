/**
 * The card „Agent" of the settings page: the agent's name, the conversation language, and the model
 * and thinking level of the note-taker and the reviewer. The choices and their labels come from the
 * backend's config module (`SettingsPage`), so this card never lists a value itself.
 */
import { useId } from "react";
import { api, type Option, type Settings, type SettingsPage } from "../../api/client";
import { InfoButton } from "../../layout/InfoButton";
import { useTeamValue } from "./useTeamValue";

const settingsOf = (page: SettingsPage) => page.settings;

export function AgentSettingsCard() {
  const card = useTeamValue({
    load: api.settings,
    toDraft: settingsOf,
    save: api.saveSettings,
    reset: api.resetSettings,
    resetText: "Die Agent-Einstellungen werden auf den Standard zurückgesetzt. Ihre Änderungen gehen verloren.",
  });
  const page = card.stored;
  const draft = card.draft;

  // The selects offer only the backend's options, so their values are always valid settings values.
  function update(field: keyof Settings, value: string) {
    if (draft) card.setDraft({ ...draft, [field]: value } as Settings);
  }

  return (
    <section className="card">
      <h2>Agent</h2>
      {card.error && <p className="error card-error" role="alert">{card.error}</p>}
      {page && draft && (
        <form className="form" onSubmit={card.save}>
          <label className="field">
            Name des Agenten
            <input required value={draft.agent_name} onChange={(event) => update("agent_name", event.target.value)} />
          </label>
          <SelectField label="Gesprächssprache" options={page.languages} value={draft.language} onChange={(value) => update("language", value)} />
          <div className="form-grid">
            <SelectField
              label="Protokollant: Modell"
              info="Die KI im Hintergrund, die nachschlägt und die Antworten aufschreibt."
              options={page.models}
              value={draft.note_taker_model}
              onChange={(value) => update("note_taker_model", value)}
            />
            <SelectField label="Protokollant: Denkstufe" options={page.thinking_levels} value={draft.note_taker_thinking} onChange={(value) => update("note_taker_thinking", value)} />
            <SelectField
              label="Prüfer: Modell"
              info="Die KI, die die Antworten prüft und Rückfragen auswählt."
              options={page.models}
              value={draft.reviewer_model}
              onChange={(value) => update("reviewer_model", value)}
            />
            <SelectField label="Prüfer: Denkstufe" options={page.thinking_levels} value={draft.reviewer_thinking} onChange={(value) => update("reviewer_thinking", value)} />
          </div>
          <div className="form-actions">
            <button className="button button-primary" disabled={!card.changed || card.busy}>Speichern</button>
            <button type="button" className="button" disabled={card.busy} onClick={card.reset}>Auf Standard zurücksetzen</button>
          </div>
        </form>
      )}
    </section>
  );
}

type SelectFieldProps = { label: string; info?: string; options: Option[]; value: string; onChange: (value: string) => void };

function SelectField({ label, info, options, value, onChange }: SelectFieldProps) {
  const id = useId();
  return (
    <div className="field">
      <span className="with-info">
        <label htmlFor={id}>{label}</label>
        {info && <InfoButton label={label}>{info}</InfoButton>}
      </span>
      <select id={id} value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => (
          <option key={option.value} value={option.value}>{option.label}</option>
        ))}
      </select>
    </div>
  );
}
