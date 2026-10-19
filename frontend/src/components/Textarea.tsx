import { useId, type TextareaHTMLAttributes } from "react";

interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label: string;
  hint?: string;
  error?: string;
}

/** Labelled multi-line text field. Errors are linked with aria-describedby, like Input. */
export function Textarea({ label, hint, error, id, className = "", rows = 4, ...rest }: TextareaProps) {
  const generatedId = useId();
  const fieldId = id ?? generatedId;
  const hintId = hint ? `${fieldId}-hint` : undefined;
  const errorId = error ? `${fieldId}-error` : undefined;
  return (
    <div className={`pc-field ${className}`.trim()}>
      <label className="pc-field__label" htmlFor={fieldId}>
        {label}
      </label>
      <textarea
        id={fieldId}
        className="pc-input pc-textarea"
        rows={rows}
        aria-invalid={error ? true : undefined}
        aria-describedby={[hintId, errorId].filter(Boolean).join(" ") || undefined}
        {...rest}
      />
      {hint && (
        <p id={hintId} className="pc-field__hint">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} className="pc-field__error" role="alert">
          <span aria-hidden="true">⚠ </span>
          {error}
        </p>
      )}
    </div>
  );
}
