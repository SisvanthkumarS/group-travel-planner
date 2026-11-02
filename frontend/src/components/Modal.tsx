import { useEffect, useId, useRef, type ReactNode } from 'react';

type ModalProps = {
  title: string;
  subtitle?: ReactNode;
  onClose: () => void;
  children: ReactNode;
  size?: 'md' | 'lg';
};

/**
 * Native <dialog> opened with showModal(): the browser handles focus trapping,
 * Escape and the backdrop, and keeps the page behind it inert.
 */
export function Modal({
  title,
  subtitle,
  onClose,
  children,
  size = 'md',
}: ModalProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal();
    return () => dialog?.close();
  }, []);

  return (
    <dialog
      ref={ref}
      className={`modal modal--${size}`}
      aria-labelledby={titleId}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
    >
      <div className="modal__header">
        <div className="modal__heading">
          <h2 id={titleId} className="modal__title">
            {title}
          </h2>
          {subtitle && <span className="modal__subtitle">{subtitle}</span>}
        </div>
        <button
          type="button"
          className="icon-btn"
          aria-label="Close"
          onClick={onClose}
        >
          <svg
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            aria-hidden="true"
          >
            <path d="M6 6l12 12M18 6L6 18" />
          </svg>
        </button>
      </div>
      <div className="modal__body">{children}</div>
    </dialog>
  );
}

type ConfirmProps = {
  title: string;
  children: ReactNode;
  confirmLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
  busy?: boolean;
  error?: string | null;
  danger?: boolean;
};

/** Yes/no confirmation, e.g. deleting a trip (US-12) or cancelling an activity (US-16). */
export function ConfirmDialog({
  title,
  children,
  confirmLabel,
  onConfirm,
  onCancel,
  busy = false,
  error,
  danger = false,
}: ConfirmProps) {
  return (
    <Modal title={title} onClose={onCancel}>
      <div className="stack">
        <div className="confirm__text">{children}</div>
        {error && (
          <div className="form-error" role="alert">
            {error}
          </div>
        )}
        <div className="actions">
          <button
            type="button"
            className="btn btn--secondary"
            onClick={onCancel}
            disabled={busy}
          >
            Keep it
          </button>
          <button
            type="button"
            className={`btn ${danger ? 'btn--danger' : 'btn--primary'}`}
            onClick={onConfirm}
            disabled={busy}
          >
            {busy ? 'Working…' : confirmLabel}
          </button>
        </div>
      </div>
    </Modal>
  );
}
