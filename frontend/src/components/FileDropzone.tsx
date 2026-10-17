import { useId, useRef, useState, type DragEvent } from "react";
import { formatFileSize } from "../lib/format";
import { Button } from "./Button";


interface FileDropzoneProps {
  label: string;
  accept: string;
  hint: string;
  file?: File;
  error?: string;
  onFile: (file: File) => void;
  onClear: () => void;
}

/**
 * Drag-and-drop area with a keyboard-accessible "Choose file" button. Once a file is chosen it
 * shows the name and size with an option to choose a different one.
 */
export function FileDropzone({ label, accept, hint, file, error, onFile, onClear }: FileDropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const inputId = useId();
  const [dragging, setDragging] = useState(false);
  const errorId = error ? `${inputId}-error` : undefined;

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setDragging(false);
    const dropped = e.dataTransfer.files?.[0];
    if (dropped) onFile(dropped);
  }

  return (
    <div className="pc-field">
      <span className="pc-field__label" id={`${inputId}-label`}>
        {label}
      </span>
      {file ? (
        <div className="pc-dropzone__chosen">
          <span className="pc-dropzone__icon" aria-hidden="true">
            📄
          </span>
          <div className="pc-dropzone__meta">
            <span className="pc-dropzone__name">{file.name}</span>
            <span className="pc-field__hint">{formatFileSize(file.size)}</span>
          </div>
          <Button variant="ghost" onClick={onClear}>
            Choose a different file
          </Button>
        </div>
      ) : (
        <div
          className={`pc-dropzone ${dragging ? "pc-dropzone--active" : ""} ${error ? "pc-dropzone--error" : ""}`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
        >
          <p className="pc-dropzone__title">Drag and drop your document here</p>
          <p className="pc-dropzone__or">or</p>
          <Button
            variant="secondary"
            onClick={() => inputRef.current?.click()}
            aria-describedby={[`${inputId}-hint`, errorId].filter(Boolean).join(" ")}
            aria-invalid={error ? true : undefined}
          >
            Choose file
          </Button>
          <p className="pc-field__hint" id={`${inputId}-hint`}>
            {hint}
          </p>
        </div>
      )}
      <input
        ref={inputRef}
        id={inputId}
        type="file"
        accept={accept}
        className="visually-hidden"
        tabIndex={-1}
        aria-labelledby={`${inputId}-label`}
        onChange={(e) => {
          const chosen = e.target.files?.[0];
          e.target.value = "";
          if (chosen) onFile(chosen);
        }}
      />
      {error && (
        <p id={errorId} className="pc-field__error" role="alert">
          <span aria-hidden="true">⚠ </span>
          {error}
        </p>
      )}
    </div>
  );
}
