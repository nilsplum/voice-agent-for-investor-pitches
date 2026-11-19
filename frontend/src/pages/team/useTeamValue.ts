/**
 * The one behaviour of a team-editable value's card on the settings page, mirroring the backend's
 * one rule for these values (backend/app/team_values.py): load the stored value, edit a local draft,
 * „Speichern" (only once something changed) and „Auf Standard zurücksetzen" (after a confirmation).
 * After saving or resetting, the card shows what the backend returned, which is what it stored.
 * Errors appear inline in the card; success is a toast.
 *
 * `load` and `toDraft` must be stable (module-level) functions, because the value is loaded once.
 */
import { useEffect, useState, type FormEvent } from "react";
import { errorMessage } from "../../api/client";
import { useConfirm, useNotify } from "../../notifications/NotificationsProvider";

type Options<Stored, Draft> = {
  load: () => Promise<Stored>;
  toDraft: (stored: Stored) => Draft;
  save: (draft: Draft) => Promise<Stored>;
  reset: () => Promise<Stored>;
  resetText: string; // what the reset confirmation says will be reset
};

export function useTeamValue<Stored, Draft>({ load, toDraft, save, reset, resetText }: Options<Stored, Draft>) {
  const notify = useNotify();
  const confirm = useConfirm();
  const [stored, setStored] = useState<Stored | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function show(value: Stored) {
    setStored(value);
    setDraft(toDraft(value));
    setError(null);
  }

  useEffect(() => {
    load().then(show, (failure: unknown) => setError(errorMessage(failure)));
  }, [load, toDraft]);

  async function run(action: () => Promise<Stored>, success: string) {
    setBusy(true);
    setError(null);
    try {
      show(await action());
      notify(success);
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(false);
    }
  }

  // Compared as JSON: the draft is plain data, and the order of a list matters too.
  const changed = stored !== null && draft !== null && JSON.stringify(draft) !== JSON.stringify(toDraft(stored));

  return {
    stored,
    draft,
    setDraft,
    changed,
    error,
    busy,
    save(event: FormEvent) {
      event.preventDefault();
      if (draft !== null) void run(() => save(draft), "Gespeichert.");
    },
    async reset() {
      const confirmed = await confirm({
        title: "Auf Standard zurücksetzen?",
        text: resetText,
        confirmLabel: "Zurücksetzen",
        danger: true,
      });
      if (confirmed) await run(reset, "Auf Standard zurückgesetzt.");
    },
  };
}
