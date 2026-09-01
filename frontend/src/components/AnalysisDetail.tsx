import type { AnalyzeResponse } from '../types'
import { CommentDiff } from './CommentDiff'

/** The full analysis view — band table, token, comment diff. Shared by the
 *  single panel and the batch accordion. */
export function AnalysisDetail({ data }: { data: AnalyzeResponse }) {
  return (
    <div className="analysis-detail">
      <table className="bands">
        <thead>
          <tr>
            <th>band</th>
            <th>range</th>
            <th>dBFS</th>
            <th>digit</th>
          </tr>
        </thead>
        <tbody>
          {data.bands.map((b) => (
            <tr key={b.band} title={`RMS ${b.rms.toFixed(5)}`}>
              <td>{b.band}</td>
              <td>
                {b.hz_low.toFixed(0)}&ndash;{b.hz_high.toFixed(0)}&nbsp;Hz
              </td>
              <td>{b.dbfs.toFixed(1)}</td>
              <td className="digit">{b.digit}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="token-line">
        token <code className="token">{data.token}</code>
        <span
          className="muted"
          title={`Audio is downsampled to ${data.sample_rate} Hz for analysis (only 20–150 Hz matters)`}
        >
          {' '}
          · {data.duration_sec.toFixed(0)}s track · analysed at {data.sample_rate} Hz
        </span>
      </div>

      <CommentDiff
        current={data.current_comment}
        proposed={data.proposed_comment}
        action={data.merge_action}
      />

      {data.existing_tokens > 1 && (
        <p className="warn">
          {data.existing_tokens} existing tokens found — all removed, replaced by one.
        </p>
      )}
    </div>
  )
}
