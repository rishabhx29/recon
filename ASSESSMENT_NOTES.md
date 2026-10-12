# Assessment Notes — Recon

A bank reconciliation tool for fund administrators. A GP imports a bank
statement CSV, the system suggests which capital call line item each incoming
payment belongs to and explains why, and approving a suggestion updates how
much that LP has funded.

## Running it from a fresh clone

Requires Python 3.11+, PostgreSQL 14+, and Node 20+.

```bash
git clone https://github.com/rishabhx29/recon.git
cd recon

python -m venv .venv
.venv\Scripts\activate          # Windows; source .venv/bin/activate elsewhere
pip install -r requirements.txt

# create the database (one time)
psql -U postgres -d postgres -c "CREATE DATABASE recon;"
psql -U postgres -d postgres -c "CREATE USER recon_app WITH PASSWORD 'pick-one';"
psql -U postgres -d recon -c "GRANT ALL ON SCHEMA public TO recon_app;"
psql -U postgres -d postgres -c "ALTER ROLE recon_app CREATEDB;"   # lets the test runner make test_recon

cp .env.example .env             # then fill in DATABASE_PASSWORD and SECRET_KEY

python manage.py migrate
python manage.py seed_demo

python manage.py runserver       # backend on :8000
cd frontend && npm install && npm run dev    # frontend on :5173
```

Open http://localhost:5173 and pick an organization from the rail. The Vite
dev server proxies `/api` to Django, so there is no CORS configuration and
no second origin in development.

`GET /api/health` returns `{"ok": true}` if the API is up and can reach the
database. It is the quickest way to tell a backend problem from a frontend
one.

### Tests

```bash
python manage.py test
```

44 tests, all passing. They cover the eight required cases plus normalisation,
per-row import errors, cross-tenant isolation, seed idempotency, and a
two-thread concurrency test that proves a line item cannot be funded twice —
two 8,000 wires against a 10,000 line item, released together, of which exactly
one may succeed.

### Screen recording

I was not able to produce the walkthrough recording. I would rather say so than
send something I did not make. The parts it was meant to cover are all
reachable in about two minutes by hand:

```bash
python manage.py seed_demo    # run it twice, the counts do not change
```

Then open the React page, upload `docs/sample_bank_statement.csv`, and the
import summary reports the imported count, the duplicate skipped inside the
file, and the two invalid rows with their line numbers. The transaction table
shows the suggestion reasons, the overpayment that produced no match, and the
row with two candidates. Approving one updates the line item panel and rejects
the other candidate. Switching organization in the left rail shows a different
tenant's data and a 404 on anything that belongs to the first.

`NEED_REVIEW.md` records what I would have pointed at while recording.

## Data model

Every row belongs to exactly one organization, and that is a real column
rather than a convention — a query cannot accidentally cross tenants without
someone going out of their way to make it.

- **Organization** — `slug` is what the `X-Organization` header carries.
- **InvestorEntity** — the legal entity an LP invests through ("Patel Family
  Trust"). This is the name the bank shows in wire descriptions, so it is the
  string matching works against. Unique per organization.
- **CapitalCall** — `call_date` and `due_date`. A payment is only eligible for
  a line item whose call was issued on or before the payment date.
- **LineItem** — one LP's share of one call. `amount_called`,
  `amount_funded`, and a stored `status` (`open`, `partially_funded`,
  `funded`).
- **BankTransaction** — one statement row. Signed `amount` (credits positive,
  debits negative), the bank's `bank_reference`, and a `status`
  (`suggested`, `needs_review`, `reconciled`, `ignored`).
- **Match** — a proposed link from a transaction to a line item, with a
  `reason` sentence and a `status` (`proposed`, `approved`, `rejected`).

Three decisions worth stating:

**Money is `Decimal` everywhere.** `DecimalField(max_digits=14,
decimal_places=2)` maps to Postgres `numeric`, which stores exact base-10
digits. Binary floats cannot represent `0.10`, so summing them drifts. The
API serialises decimals as JSON strings for the same reason.

**`remaining` is a property, `status` is a column.** If `remaining` were
stored, three columns would need updating together and a missed update is
silent corruption. `status` *is* filtered on, so it belongs in the database —
written in exactly one place, `refresh_status()`, immediately after
`amount_funded` changes. The cost is that `remaining` cannot be used in a
query, so the eligibility filter is phrased as `amount_funded <
amount_called`.

**`(organization, bank_reference)` is unique.** This is the database-level
guarantee that a bank reference can only be imported once per organization.
Two organizations may legitimately hold the same reference, which is why the
constraint is composite rather than on the reference alone.

`Match.organization` is denormalized from the transaction. That keeps every
scoped lookup to one indexed query and keeps the isolation pattern identical
across all six models; the cost is that the copy must be set from the
transaction, which the service does.

## API

Organization is chosen with the `X-Organization` header. A missing header is
`400`; an unknown slug is `404`; a record belonging to another organization is
`404`, never `403` — the two cases are deliberately indistinguishable from the
outside.

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/health` | no header needed; liveness check |
| `GET` | `/api/organizations` | no header needed; the switcher loads before one is chosen |
| `POST` | `/api/import` | multipart upload; returns the import summary |
| `GET` | `/api/transactions` | with matches and reasons, newest first; `?status=` filter |
| `GET` | `/api/line-items` | called / funded / remaining / status |
| `POST` | `/api/matches/{id}/approve` | funds the line item; `409` if already approved or no longer covered |
| `POST` | `/api/matches/{id}/reject` | `409` if already approved |
| `POST` | `/api/transactions/{id}/ignore` | `409` if reconciled or already ignored |

Errors are always `{"detail": "..."}`.

## Matching

Run once per import, on each new credit. Only eligible line items are
considered: same organization, `remaining > 0`, and `call_date <=
transaction.date`.

1. **Reference check.** Look for an eligible line item whose normalised
   reference appears in the description or the bank reference. One found and
   the amount fits → `suggested`. One found but the amount exceeds remaining →
   `needs_review` with **no match**, because proposing something that cannot
   be approved invites a 409. Several found → propose all, `needs_review`.
2. **Name and amount check**, only when no reference matched. The investor
   name must appear as whole words in the description *and* the amount must
   equal remaining exactly. One → `suggested`. Several → propose all. None →
   `needs_review` with no matches.

Reference normalisation deletes non-alphanumerics; name normalisation
replaces them with spaces so word boundaries survive. The description is
collapsed reference-style for the reference check and name-style for the name
check — using the wrong one makes a whole rule unreachable, because `CC-1003`
can never appear inside a description normalised to `CC 1003`.

Suggestions are computed once at import. Approval re-checks the amount, since
other payments may have consumed the remaining balance in between.

## Assumptions and trade-offs

- **A missing CSV column rejects the entire file** and saves nothing, which
  is why `read_header` raises before the database is touched.
- **Invalid rows are skipped and reported** with their physical file line
  number, counting the header as line 1. `reader.line_num` is used rather than
  `enumerate` because `enumerate` counts records and drifts as soon as a quoted
  description wraps onto a second line.
- **Blank lines are skipped silently.** A trailing newline is not an error.
- **Extra columns beyond the five are ignored.**
- **Line-item references are not unique.** The brief never promises one
  appears once, and the matching rules explicitly handle multiple candidates,
  so a constraint would break a required case.
- **Amounts wider than the column are reported as row errors**, not left to
  fail the insert. `numeric(14, 2)` allows twelve digits before the point;
  anything wider would roll back an entire otherwise-good import.
- **A non-UTF-8 file returns `400`**, not a 500. Latin-1 exports are common
  enough from European banks to be worth handling.
- **Reject is idempotent; ignore is not.** Re-clicking reject on an
  already-rejected match is a harmless no-op; ignoring twice is a client bug
  worth surfacing.
- **Rejecting an approved match is a `409`** — you cannot un-fund a line item
  by clicking the wrong button. The brief does not specify this case.
- **`organization_from` stayed a helper function** rather than becoming a
  DRF mixin. With seven endpoints a mixin hides one line behind inheritance
  for no gain; `self.request` indirection would cost more than it saves.
- **The frontend is plain JavaScript, not TypeScript.** The API is
  self-describing through serializers and the risk in this problem is in the
  reconciliation rules, not in prop shapes.
- **JavaScript performs the summary totals with `Number()`.** Display-only and
  never sent back to the server. The backend remains the only place money is a
  `Decimal`.

## What I would do next

- Compute the summary strip's totals on the server so the frontend never
  touches money arithmetic at all.
- Add pagination to `/api/transactions` — `Meta.ordering` is set, but a
  few thousand rows will need a cursor eventually.
- Move the Airtable sync to a management command rather than running it
  inline on import, so a slow HTTP call never sits in the import transaction.
- Add a real reconciliation report export.

> I completed this assessment without using AI assistance.