/**
 * The card „Fragenkatalog" of the settings page: add, edit, remove and reorder the questions. Every
 * question behaves the same, „Sonstiges" too; nothing is locked. All changes stay local until
 * „Speichern". The backend assigns the IDs of new questions (sent without one) and never hands out
 * an ID twice, so this card only keeps the IDs it received.
 */
import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";
import { useId } from "react";
import { api, type Catalog, type CatalogQuestionEdit } from "../../api/client";
import { InfoButton } from "../../layout/InfoButton";
import { useTeamValue } from "./useTeamValue";

// `key` identifies a block for React while new questions have no ID yet.
type DraftQuestion = CatalogQuestionEdit & { key: string };

const toDraft = (catalog: Catalog): DraftQuestion[] =>
  catalog.questions.map(({ id, topic, question, context }) => ({ key: `question-${id}`, id, topic, question, context }));

const saveDraft = (draft: DraftQuestion[]) =>
  api.saveCatalog({ questions: draft.map(({ id, topic, question, context }) => ({ id, topic, question, context })) });

export function CatalogCard() {
  const card = useTeamValue({
    load: api.catalog,
    toDraft,
    save: saveDraft,
    reset: api.resetCatalog,
    resetText: "Der Fragenkatalog wird auf den Standard zurückgesetzt. Ihre Änderungen gehen verloren.",
  });
  const draft = card.draft;

  function change(index: number, field: "topic" | "question" | "context", value: string) {
    if (draft) card.setDraft(draft.map((question, i) => (i === index ? { ...question, [field]: value } : question)));
  }

  function move(index: number, by: -1 | 1) {
    if (!draft) return;
    const moved = [...draft];
    [moved[index], moved[index + by]] = [moved[index + by], moved[index]];
    card.setDraft(moved);
  }

  function remove(index: number) {
    if (draft) card.setDraft(draft.filter((_, i) => i !== index));
  }

  function add() {
    if (draft) card.setDraft([...draft, { key: crypto.randomUUID(), id: null, topic: "", question: "", context: "" }]);
  }

  return (
    <section className="card">
      <h2>Fragenkatalog</h2>
      {card.error && <p className="error card-error" role="alert">{card.error}</p>}
      {draft && (
        <form className="form" onSubmit={card.save}>
          {draft.map((question, index) => (
            <QuestionBlock
              key={question.key}
              question={question}
              number={index + 1}
              first={index === 0}
              last={index === draft.length - 1}
              only={draft.length === 1}
              onChange={(field, value) => change(index, field, value)}
              onMove={(by) => move(index, by)}
              onRemove={() => remove(index)}
            />
          ))}
          <div>
            <button type="button" className="button" onClick={add}>
              <Plus size={16} aria-hidden /> Frage hinzufügen
            </button>
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

type QuestionBlockProps = {
  question: DraftQuestion;
  number: number;
  first: boolean;
  last: boolean;
  only: boolean; // the catalog needs at least one question, so the only one cannot be removed
  onChange: (field: "topic" | "question" | "context", value: string) => void;
  onMove: (by: -1 | 1) => void;
  onRemove: () => void;
};

function QuestionBlock({ question, number, first, last, only, onChange, onMove, onRemove }: QuestionBlockProps) {
  const contextId = useId();
  const title = `Frage ${number}`;
  return (
    <div className="question-block" role="group" aria-label={title}>
      <div className="question-head">
        <h3>{title}</h3>
        <div className="icon-buttons">
          <button type="button" className="icon-button" title="Nach oben" aria-label={`${title} nach oben`} disabled={first} onClick={() => onMove(-1)}>
            <ArrowUp size={18} aria-hidden />
          </button>
          <button type="button" className="icon-button" title="Nach unten" aria-label={`${title} nach unten`} disabled={last} onClick={() => onMove(1)}>
            <ArrowDown size={18} aria-hidden />
          </button>
          <button type="button" className="icon-button" title="Entfernen" aria-label={`${title} entfernen`} disabled={only} onClick={onRemove}>
            <Trash2 size={18} aria-hidden />
          </button>
        </div>
      </div>
      <label className="field">
        Thema
        {/* A new question gets the focus, so the team can type at once after „Frage hinzufügen". */}
        <input required autoFocus={question.id === null} value={question.topic} onChange={(event) => onChange("topic", event.target.value)} />
      </label>
      <label className="field">
        Frage
        <textarea required rows={2} value={question.question} onChange={(event) => onChange("question", event.target.value)} />
      </label>
      <div className="field">
        <span className="with-info">
          <label htmlFor={contextId}>Kontext</label>
          <InfoButton label="Kontext">
            Was eine vollständige Antwort abdeckt. Der Agent nutzt das, um die Frage zu erklären, der Prüfer, um die
            Antwort zu prüfen.
          </InfoButton>
        </span>
        <textarea id={contextId} required rows={3} value={question.context} onChange={(event) => onChange("context", event.target.value)} />
      </div>
    </div>
  );
}
