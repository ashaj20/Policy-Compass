import { useId } from "react";

interface RadioOption {
  value: string;
  label: string;
  description?: string;
}

interface RadioGroupProps {
  legend: string;
  name: string;
  options: RadioOption[];
  value: string;
  onChange: (value: string) => void;
  error?: string;
  hint?: string;
}

/** A labelled set of radio cards. Arrow keys move between options (native radio behaviour). */
export function RadioGroup({ legend, name, options, value, onChange, error, hint }: RadioGroupProps) {
  const id = useId();
  const errorId = error ? `${id}-error` : undefined;
  const hintId = hint ? `${id}-hint` : undefined;
  return (
    <fieldset
      className="pc-radio-group"
      aria-describedby={[hintId, errorId].filter(Boolean).join(" ") || undefined}
      aria-invalid={error ? true : undefined}
    >
      <legend className="pc-field__label">{legend}</legend>
      {hint && (
        <p id={hintId} className="pc-field__hint">
          {hint}
        </p>
      )}
      <div className="pc-radio-group__options">
        {options.map((o) => (
          <label key={o.value} className={`pc-radio ${value === o.value ? "pc-radio--checked" : ""}`}>
            <input
              type="radio"
              name={name}
              value={o.value}
              checked={value === o.value}
              onChange={() => onChange(o.value)}
              aria-invalid={error ? true : undefined}
            />
            <span className="pc-radio__text">
              <span className="pc-radio__label">{o.label}</span>
              {o.description && <span className="pc-radio__description">{o.description}</span>}
            </span>
          </label>
        ))}
      </div>
      {error && (
        <p id={errorId} className="pc-field__error">
          <span aria-hidden="true">⚠ </span>
          {error}
        </p>
      )}
    </fieldset>
  );
}
