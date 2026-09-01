import { useEffect } from 'react'
import { useAnalyze } from '../hooks/useAnalyze'
import type { Track } from '../types'
import { CommentDiff } from './CommentDiff'

export function AnalyzePanel({ track }: { track: Track }) {
  const { data, loading, error, analyze, reset } = useAnalyze()

  // clear stale results when the selected track changes
  useEffect(() => {
    reset()
  }, [track.id, reset])

  return (
    <div className="analyze">
      <div className="analyze-head">
        <div className="analyze-title">
          <strong>{track.title || '—'}</strong>
          <span className="muted"> — {track.artist || '—'}</span>
        </div>
        <button
          onClick={() => analyze(track.id)}
          disabled={loading || !track.has_file}
          title={track.has_file ? undefined : 'no local audio file'}
        >
          {loading ? 'Analyzing…' : 'Analyze audio'}
        </button>
      </div>

      {!track.has_file && (
        <p className="muted">No local audio file — analysis unavailable for this track.</p>
      )}
      {error && <p className="error">Analysis failed: {error}</p>}

      {data && (
        <>
          <table className="bands">
            <thead>
              <tr>
                <th>band</th>
                <th>range</th>
                <th>RMS</th>
                <th>dBFS</th>
                <th>digit</th>
              </tr>
            </thead>
            <tbody>
              {data.bands.map((b) => (
                <tr key={b.band}>
                  <td>{b.band}</td>
                  <td>
                    {b.hz_low.toFixed(0)}–{b.hz_high.toFixed(0)} Hz
                  </td>
                  <td>{b.rms.toFixed(5)}</td>
                  <td>{b.dbfs.toFixed(1)}</td>
                  <td className="digit">{b.digit}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="token-line">
            token <code className="token">{data.token}</code>
            <span className="muted">
              {' '}
              · {data.duration_sec.toFixed(0)}s @ {data.sample_rate} Hz
            </span>
          </div>

          <CommentDiff
            current={data.current_comment}
            proposed={data.proposed_comment}
            action={data.merge_action}
          />

          {data.existing_tokens > 1 && (
            <p className="warn">
              {data.existing_tokens} existing tokens found — only the first is replaced.
            </p>
          )}
          <p className="muted">Saving to Rekordbox comes in step 5.</p>
        </>
      )}
    </div>
  )
}
