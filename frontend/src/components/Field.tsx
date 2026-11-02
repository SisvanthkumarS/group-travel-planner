import { useId, type InputHTMLAttributes, type ReactNode } from 'react';

type FieldProps = InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  error?: ReactNode;
  hint?: ReactNode;
};

/** Labelled input with an error or hint wired up for screen readers. */
export function Field({ label, error, hint, ...input }: FieldProps) {
  const id = useId();
  const messageId = `${id}-message`;
  const hasMessage = Boolean(error || hint);

  return (
    <div className="field">
      <label htmlFor={id} className="field__label">
        {label}
      </label>
      <input
        id={id}
        className="field__input"
        aria-invalid={error ? true : undefined}
        aria-describedby={hasMessage ? messageId : undefined}
        {...input}
      />
      {error ? (
        <span id={messageId} className="field__error">
          {error}
        </span>
      ) : hint ? (
        <span id={messageId} className="field__hint">
          {hint}
        </span>
      ) : null}
    </div>
  );
}
