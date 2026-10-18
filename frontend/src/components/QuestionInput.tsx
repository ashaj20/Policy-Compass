import { useId, useState, type FormEvent, type KeyboardEvent } from "react";
import { validateQuestion } from "../lib/questions";
import { Button } from "./Button";

interface QuestionInputProps {
  label?: string;
  placeholder?: string;
  examples?: string[];
  busy?: boolean;
  initialValue?: string;
  onAsk: (question: string) => void;
}

/**
 * The question box (US-016). Enter submits, Shift+Enter adds a new line. Examples fill and
 * submit the box. The label is always available to screen readers.
 */
export function QuestionInput({
  label = "What do you need to know?",
  placeholder = "Type your question…",
  examples = [],
  busy = false,
  initialValue = "",
  onAsk,
}: QuestionInputProps) {
  const id = useId();
  const [value, setValue] = useState(initialValue);
  const [error, setError] = useState<string>();

  function submit(question: string) {
    const problem = validateQuestion(question);
    setError(problem);
    if (!problem) onAsk(question.trim());
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    submit(value);
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit(value);
    }
  }

  return (
    <form className="pc-question" onSubmit={onSubmit} noValidate role="search">
      <label htmlFor={id} className="pc-question__label">
        {label}
      </label>
      <div className="pc-question__row">
        <textarea
          id={id}
          className="pc-question__input"
          rows={2}
          placeholder={placeholder}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={onKeyDown}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${id}-error` : `${id}-hint`}
          maxLength={1200}
        />
        <Button type="submit" loading={busy} className="pc-question__ask">
          Ask
        </Button>
      </div>
      {error ? (
        <p id={`${id}-error`} className="pc-field__error" role="alert">
          <span aria-hidden="true">⚠ </span>
          {error}
        </p>
      ) : (
        <p id={`${id}-hint`} className="pc-field__hint">
          Press Enter to ask. Please don't include personal information.
        </p>
      )}
      {examples.length > 0 && (
        <div className="pc-question__examples">
          <span className="pc-field__hint">Examples:</span>
          {examples.map((example) => (
            <button
              key={example}
              type="button"
              className="pc-chip"
              disabled={busy}
              onClick={() => {
                setValue(example);
                submit(example);
              }}
            >
              {example}
            </button>
          ))}
        </div>
      )}
    </form>
  );
}
