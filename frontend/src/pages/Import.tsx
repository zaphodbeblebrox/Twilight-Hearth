import { useEffect, useRef, useState } from "react";
import { api, type Imported } from "../api";
import { Problem } from "../components";

const FILES = "image/*,.heic,.pdf,.docx,.txt,.md,.html,.htm,.json";

export function ImportDialog({ onClose, onImport }: { onClose: () => void; onImport: (result: Imported) => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const open = useRef(true);
  const [source, setSource] = useState<"file" | "url">("file");
  const [file, setFile] = useState<File | null>(null);
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    open.current = true;
    const element = dialog.current;
    element?.showModal();
    return () => {
      open.current = false;
      element?.close();
    };
  }, []);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      let result: Imported;
      if (source === "url") {
        result = await api<Imported>("imports/url", "POST", { url });
      } else {
        const form = new FormData();
        form.append("file", file!);
        result = await api<Imported>("imports/file", "POST", form);
      }
      // A result that arrives after the dialog was closed must not replace the page.
      if (open.current) onImport(result);
    } catch (problem) {
      setError(problem);
    } finally {
      setBusy(false);
    }
  }

  const choice = (value: typeof source, label: string) => (
    <label className="flex items-center gap-2">
      <input
        type="radio"
        name="source"
        checked={source === value}
        disabled={busy}
        onChange={() => {
          setSource(value);
          setError(null);
        }}
      />
      {label}
    </label>
  );

  return (
    <dialog
      ref={dialog}
      aria-labelledby="import-title"
      className="m-auto w-full max-w-md rounded-xl p-5 text-dusk-900 backdrop:bg-dusk-900/50"
      onCancel={(event) => {
        // Also sent when the file picker is cancelled, which must not close this.
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <form onSubmit={submit} className="space-y-4">
        <h2 id="import-title" className="text-2xl">Import a recipe</h2>
        <div className="flex gap-5">
          {choice("file", "File or photo")}
          {choice("url", "Web address")}
        </div>
        {source === "file" ? (
          <label className="block">
            <span className="label">Photo, PDF, Word, text or saved web page</span>
            <input key="file" type="file" required accept={FILES} disabled={busy} onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </label>
        ) : (
          <label className="block">
            <span className="label">Address of the recipe page</span>
            <input key="url" className="field" inputMode="url" required maxLength={2000} placeholder="https://" disabled={busy} value={url} onChange={(e) => setUrl(e.target.value)} />
          </label>
        )}
        <p className="text-sm text-dusk-500">
          You can check and change everything before saving. Photos, documents and some pages are
          read by AI from Anthropic.
        </p>
        <Problem error={error} />
        <div className="flex gap-2">
          <button className="btn-primary" disabled={busy}>{busy ? "Reading recipe…" : "Import"}</button>
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
        </div>
      </form>
    </dialog>
  );
}
