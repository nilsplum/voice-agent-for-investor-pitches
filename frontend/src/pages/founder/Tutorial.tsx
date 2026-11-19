/**
 * The short tutorial before every conversation: six slides, one icon and one sentence each, with as
 * little text as possible. It can be skipped at any slide; both ways lead to the device check.
 */
import { Headphones, ListChecks, MessageCircleQuestion, MessagesSquare, NotebookPen, OctagonX } from "lucide-react";
import { useState } from "react";

const SLIDES = [
  { icon: Headphones, text: "Suchen Sie sich einen ruhigen Ort. Kopfhörer sind optional." },
  { icon: MessagesSquare, text: "Sprechen Sie ganz natürlich. Der Agent stellt eine Frage nach der anderen." },
  { icon: MessageCircleQuestion, text: "Sie können jederzeit auch selbst Fragen stellen." },
  { icon: ListChecks, text: "Ist eine Antwort unklar, fragt der Agent einmal nach." },
  { icon: NotebookPen, text: "Der Agent beendet das Gespräch, wenn alles aufgeschrieben ist." },
  { icon: OctagonX, text: "STOPP beendet das Gespräch endgültig." },
];

export function Tutorial({ onDone }: { onDone: () => void }) {
  const [index, setIndex] = useState(0);
  const { icon: Icon, text } = SLIDES[index];
  const last = index === SLIDES.length - 1;

  return (
    <section className="card tutorial">
      <p className="muted">{index + 1} von {SLIDES.length}</p>
      <Icon className="tutorial-icon" size={48} aria-hidden />
      <p className="tutorial-text" aria-live="polite">{text}</p>
      <div className="actions">
        <button className="button" disabled={index === 0} onClick={() => setIndex(index - 1)}>Zurück</button>
        <button className="button button-primary" onClick={last ? onDone : () => setIndex(index + 1)}>
          {last ? "Zum Gerätetest" : "Weiter"}
        </button>
      </div>
      {!last && <button className="link-button" onClick={onDone}>Tutorial überspringen</button>}
    </section>
  );
}
