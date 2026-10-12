import { useState } from 'react'
import { apiFetch } from '../api'

export function ImportCard({ organization, onImported, onError }) {
  const [file, setFile] = useState(null)
  const [summary, setSummary] = useState(null)
  const [uploading, setUploading] = useState(false)

  async function upload() {
    if (!file || !organization) return
    setUploading(true)
    try {
      const form = new FormData()
      form.append('file', file)
      setSummary(
        await apiFetch('/api/import', organization, { method: 'POST', body: form }),
      )
      setFile(null)
      onImported()
    } catch (uploadError) {
      onError(uploadError.message)
      setSummary(null)
    } finally {
      setUploading(false)
    }
  }

  return (
    <section>
      <h2>Import bank statement</h2>
      <div className="import-row">
        <input
          type="file"
          accept=".csv"
          onChange={(event) => setFile(event.target.files[0])}
        />
        <button onClick={upload} disabled={!file || uploading || !organization}>
          {uploading ? 'Uploading' : 'Upload'}
        </button>
      </div>

      {summary && (
        <div className="summary">
          <p>
            Imported <strong>{summary.imported}</strong> · skipped{' '}
            <strong>{summary.duplicates}</strong> duplicate
            {summary.duplicates === 1 ? '' : 's'}
          </p>
          {summary.duplicate_lines.length > 0 && (
            <p className="muted">
              Duplicate lines: {summary.duplicate_lines.join(', ')}
            </p>
          )}
          {summary.errors.length > 0 && (
            <ul className="errors">
              {summary.errors.map((rowError) => (
                <li key={rowError.line}>
                  Line {rowError.line}: {rowError.message}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  )
}
