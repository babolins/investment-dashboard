import { useRef, useState } from "react";

interface Props {
  onUpload: (file: File) => void;
  loading: boolean;
  error: string | null;
}

export default function UploadCsv({ onUpload, loading, error }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);

  const handleFile = (f: File | undefined) => {
    if (!f) return;
    if (!f.name.endsWith(".csv") && f.type !== "text/csv") {
      alert("Please upload a CSV file exported from Fidelity.");
      return;
    }
    onUpload(f);
  };

  return (
    <div className="card upload-card">
      <h2>Upload Portfolio</h2>
      <p className="hint">
        In Fidelity, go to <strong>Accounts &amp; Trade → Portfolio → Positions</strong>, then
        click <strong>Download</strong> to export a CSV.
      </p>

      <div
        className={`drop-zone ${dragOver ? "drag-over" : ""}`}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          handleFile(e.dataTransfer.files[0]);
        }}
      >
        {loading ? (
          <span className="uploading">Parsing portfolio…</span>
        ) : (
          <>
            <span className="drop-icon">📂</span>
            <span>Drop your Fidelity CSV here, or click to browse</span>
          </>
        )}
      </div>

      <input
        ref={inputRef}
        type="file"
        accept=".csv,text/csv"
        style={{ display: "none" }}
        onChange={(e) => handleFile(e.target.files?.[0])}
      />

      {error && <p className="error-msg">{error}</p>}
    </div>
  );
}
