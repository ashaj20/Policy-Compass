import { useId, type InputHTMLAttributes } from "react";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  hint?: string;
  error?: string;
}

/** Labelled text input. Errors are linked with aria-describedby so screen readers announce them. */
export function Input({ label, hint, error, id, className = "", ...rest }: InputProps) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  const hintId = hint ? `${inputId}-hint` : undefined;
  const errorId = error ? `${inputId}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;

  return (
    <div className={`pc-field ${className}`.trim()}>
      <label className="pc-field__label" htmlFor={inputId}>
        {label}
      </label>
      {hint && (
        <p id={hintId} className="pc-field__hint">
          {hint}
        </p>
      )}
      <input
        id={inputId}
        className="pc-input"
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        {...rest}
      />
      {error && (
        <p id={errorId} className="pc-field__error">
          <span aria-hidden="true">⚠ </span>
          {error}
        </p>
      )}
    </div>
  );
}
