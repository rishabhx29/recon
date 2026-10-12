import { useCallback, useEffect, useState } from 'react'
import './App.css'
import { apiFetch } from './api'
import { formatMoney } from './format'
import { ImportCard } from './components/ImportCard'
import { LineItemsPanel } from './components/LineItemsPanel'
import { OrgSwitcher } from './components/OrgSwitcher'
import { TransactionsTable } from './components/TransactionsTable'

export default function App() {
  const [organizations, setOrganizations] = useState([])
  const [organization, setOrganization] = useState('')
  const [transactions, setTransactions] = useState([])
  const [lineItems, setLineItems] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [pending, setPending] = useState({})

  useEffect(() => {
    apiFetch('/api/organizations')
      .then((rows) => {
        setOrganizations(rows)
        setOrganization(rows[0]?.slug ?? '')
      })
      .catch((loadError) => setError(loadError.message))
  }, [])

  const refresh = useCallback(async () => {
    if (!organization) return
    setLoading(true)
    setError('')
    try {
      const [transactionPage, lineItemPage] = await Promise.all([
        apiFetch('/api/transactions', organization),
        apiFetch('/api/line-items', organization),
      ])
      setTransactions(transactionPage.results)
      setLineItems(lineItemPage.results)
    } catch (refreshError) {
      setError(refreshError.message)
    } finally {
      setLoading(false)
    }
  }, [organization])

  useEffect(() => {
    refresh()
  }, [refresh])

  async function runAction(key, request) {
    setPending((current) => ({ ...current, [key]: true }))
    setError('')
    try {
      await request()
      await refresh()
    } catch (actionError) {
      setError(actionError.message)
    } finally {
      setPending((current) => ({ ...current, [key]: false }))
    }
  }

  const counts = {
    needs_review: transactions.filter((entry) => entry.status === 'needs_review').length,
    suggested: transactions.filter((entry) => entry.status === 'suggested').length,
    reconciled: transactions.filter((entry) => entry.status === 'reconciled').length,
  }
  const funded = lineItems.reduce(
    (total, lineItem) => total + Number(lineItem.amount_funded),
    0,
  )
  const called = lineItems.reduce(
    (total, lineItem) => total + Number(lineItem.amount_called),
    0,
  )

  return (
    <div className="shell">
      <aside className="rail">
        <div className="rail-brand">
          <h1>Recon</h1>
          <span>capital call reconciliation</span>
        </div>
        <OrgSwitcher
          organizations={organizations}
          selected={organization}
          onChange={setOrganization}
        />
      </aside>

      <main className="content">
        <div className="stats">
          <div className="stat">
            <span className="stat-value">{counts.needs_review}</span>
            <span className="stat-label">needs review</span>
          </div>
          <div className="stat">
            <span className="stat-value">{counts.suggested}</span>
            <span className="stat-label">suggested</span>
          </div>
          <div className="stat">
            <span className="stat-value">{counts.reconciled}</span>
            <span className="stat-label">reconciled</span>
          </div>
          <div className="stat stat-wide">
            <span className="stat-value">{formatMoney(funded)}</span>
            <span className="stat-label">
              funded of {formatMoney(called)} called
            </span>
          </div>
        </div>

        {error && <p className="error">{error}</p>}

        <ImportCard organization={organization} onImported={refresh} onError={setError} />

        {loading ? (
          <section>
            <p className="empty">Loading transactions</p>
          </section>
        ) : (
          <>
            <TransactionsTable
              transactions={transactions}
              organization={organization}
              pending={pending}
              onAction={runAction}
            />
            <LineItemsPanel lineItems={lineItems} />
          </>
        )}
      </main>
    </div>
  )
}
