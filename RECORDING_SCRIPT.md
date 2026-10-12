# Screen recording script — 4 minutes 30 seconds

Target is ≤ 5 minutes. Do it in this order. Everything below is already
working, so rehearse once with a timer before recording.

---

## 0:00 — Terminal, setup (20s)

Show the two commands, no commentary needed:

```bash
python manage.py migrate
python manage.py seed_demo
```

Run `seed_demo` **a second time** and pause on the identical output. That is
the idempotency proof, and it takes three seconds.

> "Two runs, same counts — no duplicates."

---

## 0:20 — Browser, the empty state (10s)

Open http://localhost:5173. Bluebird is selected by default and its tables are
nearly empty. One sentence:

> "The organization switcher in the rail selects the tenant. Every query is
> scoped by it."

---

## 0:30 — Import, the main event (60s)

Switch to **Northwind**. Upload `docs/sample_bank_statement.csv`. Let the
summary land and narrate it slowly:

- **Imported 11**
- **skipped 1 duplicate** → and point at "Duplicate lines: 11" — that is the
  second copy of the wire that already appeared on line 2, caught *inside one
  file*
- **Line 13: invalid date: 2026-04-31** — April has 30 days
- **Line 14: credits must be positive** — a negative amount typed as a credit

> "Two rows rejected, the other twelve parsed, eleven imported after the
> duplicate."

---

## 1:30 — The suggestions (60s)

Scroll the table slowly. Call out four specific rows, not all eleven:

1. **A `Suggested` row with "Reference CC-1001 found; amount 7,500.00
   partially pays remaining 27,500.00"** →
   > "Partial payments are allowed, and the reason says so explicitly so a
   > reviewer knows whether approving closes the line item."

2. **The Oakridge wire with TWO candidates** →
   > "Two eligible line items at the same amount, so it proposes both and lands
   > in review. The reviewer picks."

3. **The overpayment row: "Amount 13,000.00 exceeds remaining 12,500.00"** →
   > "A single reference match that's too large produces no match at all —
   > rather than suggesting something that can't be approved."

4. **The unknown wire, no matches at all.**

Optional, if you have time: the Cedar Grove row from line 12, showing it
found nothing because CC-2001 belongs to Bluebird.

---

## 2:30 — An approval (45s)

**This is the most important 45 seconds of the recording.**

Click **Approve CC-1005** on the Oakridge row. Let the refetch happen. Then
point at the line-item panel:

> "CC-1005 is now funded and closed. CC-1006 was untouched, and the other
> candidate's match was rejected automatically."

Then approve the **Haller $20,000** row, and note the status flips to
**Partially Funded** with 7,500 remaining.

---

## 3:15 — The refusal (30s)

Go to **Bluebird** and approve the Cedar Grove match — CC-2001 goes to fully
funded, $40,000 of $40,000.

Now **switch back to Northwind** and try to approve the same payment again.

There are no buttons — so instead, demonstrate the conflict at the terminal:

```bash
curl -X POST -H "X-Organization: northwind" \
  http://localhost:8000/api/matches/1/approve
```

> "409. A line item can't be funded twice, and a record from another
> organization is a 404, not a 403."

---

## 3:45 — Tenant isolation (20s)

Switch between the two organizations in the rail. Northwind has six line items
and eleven transactions; Bluebird has one and a completely different set.

> "Same file, same rules, different tenant, different answer."

---

## 4:05 — Code tour (25s)

Open three files briefly. Do not read code aloud — explain the decision:

**`reconciliation/models.py`**
> "Decimal fields everywhere, and every model carries its organization."

**`reconciliation/services.py` — `match_transaction`**
> "The reference rule runs first; the name rule only runs if no reference
> matched."

**`approve_match`**
> "One transaction, the match row locked then the line item locked in a fixed
> order, amount re-checked inside the lock. That's what makes double funding
> impossible."

Finish on the test line:

```bash
python manage.py test
```

---

## Recording notes

- **Reset first.** Delete both organizations' transactions and re-import, so
  the numbers are the ones written above. If the DB is dirty, run
  `seed_demo` again — it is idempotent and will not double anything.
- **Cursor visible**, terminal font bumped so the output is readable.
- **Do not narrate the UI decisions.** No "I chose a warm palette because…".
  Say what the tool does, not how it looks.
- If you are over time, cut the code tour to `approve_match` alone. Everything
  else is behaviour the reviewer cares about more.