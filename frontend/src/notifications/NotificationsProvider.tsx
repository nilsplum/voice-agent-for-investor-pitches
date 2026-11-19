/**
 * The one module for transient feedback: toasts (`useNotify`) and confirmation dialogs
 * (`useConfirm`). Nothing else in the app shows transient feedback, and the browser's own
 * alert/confirm/prompt are never used.
 *
 * Toasts sit bottom right and disappear after a few seconds. `confirm` renders a native <dialog>
 * and returns a promise that resolves with the user's choice (Escape counts as cancelling); the
 * dialog focuses its cancel button („Abbrechen" unless `cancelLabel` says otherwise, like
 * „Weitersprechen" for STOPP) first, so a destructive action always needs a deliberate click.
 */
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";

type ToastKind = "success" | "error" | "info";
type Toast = { id: number; text: string; kind: ToastKind };
export type ConfirmOptions = { title: string; text: string; confirmLabel: string; cancelLabel?: string; danger?: boolean };
type PendingConfirm = ConfirmOptions & { resolve: (confirmed: boolean) => void };

const TOAST_MS = 4000;

const NotifyContext = createContext<((text: string, kind?: ToastKind) => void) | null>(null);
const ConfirmContext = createContext<((options: ConfirmOptions) => Promise<boolean>) | null>(null);

export function NotificationsProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [pending, setPending] = useState<PendingConfirm | null>(null);
  const nextId = useRef(0);
  const dialog = useRef<HTMLDialogElement>(null);

  const notify = useCallback((text: string, kind: ToastKind = "success") => {
    const id = ++nextId.current;
    setToasts((all) => [...all, { id, text, kind }]);
    setTimeout(() => setToasts((all) => all.filter((toast) => toast.id !== id)), TOAST_MS);
  }, []);

  const confirm = useCallback(
    (options: ConfirmOptions) => new Promise<boolean>((resolve) => setPending({ ...options, resolve })),
    [],
  );

  useEffect(() => {
    if (pending) dialog.current?.showModal();
  }, [pending]);

  function answer(confirmed: boolean) {
    pending?.resolve(confirmed);
    dialog.current?.close();
    setPending(null);
  }

  return (
    <NotifyContext.Provider value={notify}>
      <ConfirmContext.Provider value={confirm}>
        {children}
        <div className="toasts" role="status" aria-live="polite">
          {toasts.map((toast) => (
            <div key={toast.id} className={`toast toast-${toast.kind}`}>{toast.text}</div>
          ))}
        </div>
        {pending && (
          <dialog
            ref={dialog}
            className="dialog"
            onCancel={(event) => {
              event.preventDefault(); // Escape: answered like the cancel button, closed by answer()
              answer(false);
            }}
          >
            <h2>{pending.title}</h2>
            <p>{pending.text}</p>
            <div className="dialog-actions">
              <button className="button" onClick={() => answer(false)}>{pending.cancelLabel ?? "Abbrechen"}</button>
              <button className={`button ${pending.danger ? "button-danger" : "button-primary"}`} onClick={() => answer(true)}>
                {pending.confirmLabel}
              </button>
            </div>
          </dialog>
        )}
      </ConfirmContext.Provider>
    </NotifyContext.Provider>
  );
}

export function useNotify() {
  const notify = useContext(NotifyContext);
  if (!notify) throw new Error("useNotify() needs the NotificationsProvider around it");
  return notify;
}

export function useConfirm() {
  const confirm = useContext(ConfirmContext);
  if (!confirm) throw new Error("useConfirm() needs the NotificationsProvider around it");
  return confirm;
}
