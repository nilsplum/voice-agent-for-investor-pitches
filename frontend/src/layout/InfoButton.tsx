/**
 * The info button: a small icon that shows a longer explanation when clicked and hides it on a
 * second click, so labels and pages stay short (the rule for user-facing text in AGENTS.md). It is
 * placed in a `.with-info` row, next to the heading or label it explains; the explanation opens as
 * a full-width line below that row, so it never overflows a narrow screen.
 */
import { Info } from "lucide-react";
import { useId, useState, type ReactNode } from "react";

export function InfoButton({ label, children }: { label: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <>
      <button
        type="button"
        className="info-button"
        title="Erklärung"
        aria-label={`Erklärung zu ${label}`}
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen(!open)}
      >
        <Info size={17} aria-hidden />
      </button>
      {open && <span id={id} className="info-text">{children}</span>}
    </>
  );
}
