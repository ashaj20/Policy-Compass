import { useId, useState, type InputHTMLAttributes, type ReactNode } from "react";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  hint?: string;
  error?: string;
  /** A control shown beside the input, such as a show/hide password button. */
  action?: ReactNode;
}

/** Labelled text input. Errors are linked with aria-describedby so screen readers announce them. */
export function Input({
  label,
  hint,
  error,
  action,
  id,
  className = "",
  "aria-describedby": extraDescribedBy,
  ...rest
}: InputProps) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  const hintId = hint ? `${inputId}-hint` : undefined;
  const errorId = error ? `${inputId}-error` : undefined;
  const describedBy = [hintId, extraDescribedBy, errorId].filter(Boolean).join(" ") || undefined;

  const input = (
    <input
      id={inputId}
      className="pc-input"
      aria-invalid={error ? true : undefined}
      aria-describedby={describedBy}
      {...rest}
    />
  );

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
      {action ? (
        <div className="pc-field__row">
          {input}
          {action}
        </div>
      ) : (
        input
      )}
      {error && (
        <p id={errorId} className="pc-field__error">
          <span aria-hidden="true">⚠ </span>
          {error}
        </p>
      )}
    </div>
  );
}

type PasswordInputProps = Omit<InputProps, "type" | "action">;

export function PasswordInput(props: PasswordInputProps) {
  const [visible, setVisible] = useState(false);
  return (
    <Input
      {...props}
      type={visible ? "text" : "password"}
      action={
        <button
          type="button"
          className="pc-field__toggle"
          aria-pressed={visible}
          aria-label={visible ? `Hide ${props.label.toLowerCase()}` : `Show ${props.label.toLowerCase()}`}
          onClick={() => setVisible((v) => !v)}
        >
          {visible ? "Hide" : "Show"}
        </button>
      }
    />
  );
}
