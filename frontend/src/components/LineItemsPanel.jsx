import { formatMoney } from '../format'
import { StatusBadge } from './StatusBadge'

export function LineItemsPanel({ lineItems }) {
  return (
    <section>
      <h2>
        Capital call line items <span className="count">{lineItems.length}</span>
      </h2>
      {lineItems.length === 0 ? (
        <p className="empty">No capital calls for this organization.</p>
      ) : (
        <div className="table-wrap">
          <table>
          <thead>
            <tr>
              <th>Reference</th>
              <th>Investor</th>
              <th>Call date</th>
              <th>Due date</th>
              <th className="amount">Called</th>
              <th className="amount">Funded</th>
              <th className="amount">Remaining</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {lineItems.map((lineItem) => (
              <tr key={lineItem.id}>
                <td>{lineItem.reference}</td>
                <td>{lineItem.investor}</td>
                <td>{lineItem.capital_call.call_date}</td>
                <td>{lineItem.capital_call.due_date}</td>
                <td className="amount">{formatMoney(lineItem.amount_called)}</td>
                <td className="amount">{formatMoney(lineItem.amount_funded)}</td>
                <td className="amount">{formatMoney(lineItem.remaining)}</td>
                <td>
                  <StatusBadge status={lineItem.status} />
                </td>
              </tr>
            ))}
          </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
