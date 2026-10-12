import { apiFetch } from '../api'
import { formatMoney } from '../format'
import { StatusBadge } from './StatusBadge'

const REVIEWABLE = ['suggested', 'needs_review']

export function TransactionsTable({ transactions, organization, pending, onAction }) {
  if (transactions.length === 0) {
    return (
      <section>
        <h2>Transactions</h2>
        <p className="empty">No transactions for this organization yet.</p>
      </section>
    )
  }

  return (
    <section>
      <h2>
        Transactions <span className="count">{transactions.length}</span>
      </h2>
      <div className="table-wrap">
        <table>
        <thead>
          <tr>
            <th>Date</th>
            <th>Description</th>
            <th className="amount">Amount</th>
            <th>Status</th>
            <th>Suggested</th>
            <th>Reason</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {transactions.map((entry) => {
            const open = entry.matches.filter((match) => match.status === 'proposed')
            return (
              <tr key={entry.id} className={entry.status === 'needs_review' ? 'is-review' : ''}>
                <td>{entry.date}</td>
                <td>{entry.description}</td>
                <td className="amount">{formatMoney(entry.amount)}</td>
                <td>
                  <StatusBadge status={entry.status} />
                </td>
                <td>
                  {open.map((match) => (
                    <div key={match.id}>
                      {match.line_item.investor} ({match.line_item.reference})
                    </div>
                  ))}
                </td>
                <td className="reason">
                  {open.map((match) => (
                    <div key={match.id}>{match.reason}</div>
                  ))}
                  {entry.review_reason && <div>{entry.review_reason}</div>}
                </td>
                <td>
                  {open.map((match) => (
                    <span key={match.id} className="button-pair">
                      <button
                        disabled={Boolean(pending[`approve-${match.id}`])}
                        onClick={() =>
                          onAction(`approve-${match.id}`, () =>
                            apiFetch(`/api/matches/${match.id}/approve`, organization, {
                              method: 'POST',
                            }),
                          )
                        }
                      >
                        Approve {match.line_item.reference}
                      </button>
                      <button
                        disabled={Boolean(pending[`reject-${match.id}`])}
                        onClick={() =>
                          onAction(`reject-${match.id}`, () =>
                            apiFetch(`/api/matches/${match.id}/reject`, organization, {
                              method: 'POST',
                            }),
                          )
                        }
                      >
                        Reject
                      </button>
                    </span>
                  ))}
                  {REVIEWABLE.includes(entry.status) && (
                    <button
                      disabled={Boolean(pending[`ignore-${entry.id}`])}
                      onClick={() =>
                        onAction(`ignore-${entry.id}`, () =>
                          apiFetch(`/api/transactions/${entry.id}/ignore`, organization, {
                            method: 'POST',
                          }),
                        )
                      }
                    >
                      Ignore
                    </button>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      </div>
    </section>
  )
}
