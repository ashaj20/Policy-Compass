import { useId, type SelectHTMLAttributes } from "react";

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label: string;
  options: { value: string; label: string }[];
  error?: string;
  /** Visually hide the label (it is still announced), e.g. inside a table row. */
  hideLabel?: boolean;
}

export function Select({ label, options, error, hideLabel, id, className = "", ...rest }: SelectProps) {
  const generatedId = useId();
  const selectId = id ?? generatedId;
  const errorId = error ? `${selectId}-error` : undefined;
  return (
    <div className={`pc-field ${className}`.trim()}>
      <label className={hideLabel ? "visually-hidden" : "pc-field__label"} htmlFor={selectId}>
        {label}
      </label>
      <select
        id={selectId}
        className="pc-input pc-select"
        aria-invalid={error ? true : undefined}
        aria-describedby={errorId}
        {...rest}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      {error && (
        <p id={errorId} className="pc-field__error">
          <span aria-hidden="true">⚠ </span>
          {error}
        </p>
      )}
    </div>
  );
}
