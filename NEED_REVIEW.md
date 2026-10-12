# Needs review

Written at the end of the build, after everything in the brief was implemented,
so that the gaps are on the record rather than discovered in the interview.
Ordered by how much they would cost me, not by when I found them.

---

## 1. What the first real run of the suite caught

The suite had never been executed when I wrote it. The first run was 43 tests
with one error, and the error was in my test rather than in the application:

```
ERROR: test_thousands_separator_stores_an_exact_decimal
reconciliation.models.BankTransaction.DoesNotExist
```

The fixture row was `2026-04-03,WIRE,25,000.00,credit,FT1`. A thousands
separator has to sit inside a quoted CSV field. Unquoted, the parser split the
row, read the amount as `25` and the type as `000.00`, rejected it as
`invalid type`, and saved nothing. The brief writes that amount as
`"25,000.00"` with the quotes, so the parser was correct and my fixture was
not.

I kept the broken row as its own case, because the behaviour it fell into is
the one a reviewer is most likely to try: an unquoted separator is now asserted
to be reported as a bad row with its line number, and to import nothing.

Two things I flagged as likely failures were not. The error-string assertions
passed, which surprised me, since I wrote them from memory of `services.py`
rather than from a run. The concurrency test passed six consecutive times,
which surprised me more — it releases two threads through a `Barrier` and
asserts `[200, 409]`, and I could not tell in advance which way it would go.

The suite is now 44 tests and passes. What it still does not do is section 2.

### The test that is missing entirely

There is no single test that imports `docs/sample_bank_statement.csv` and
asserts all of its outcomes at once. Every import test builds a two-row CSV by
hand and every matching test builds a single transaction directly, so the two
halves of the pipeline are each covered in isolation and the join between them
is not covered at all. The brief's three worked examples and the acceptance
table both live in that gap.

This is the highest-value test I did not write, because it is the one that
would have caught the reference-matching bug below, and that class of bug is
what the matching rules are actually for.

---

## 2. Matching is only proven on the paths I already thought of

Section 5 says the interview will upload CSVs I have never seen, and matching is
30% of the grade. I have not tested against a file I did not design. Cases I
know are unverified:

| Input | Why I am unsure |
|---|---|
| A reference that appears **only** in the `reference` column, not the description | There is a test for it; it has not been run |
| `+25,000.00` with a leading plus | `Decimal()` accepts it, but I do not know that my code path does |
| `.50` with no leading zero | Same |
| A quoted description containing a comma or a newline | `csv.DictReader` handles it; my line numbering uses `reader.line_num` precisely because `enumerate` drifts here, but nothing proves it |
| `£` or a currency symbol in the amount | Not specified, not handled, and I would want to decide deliberately rather than by accident |
| Two line items sharing a reference **and** the same investor, one of them already funded | The eligibility filter should drop the funded one. Untested |
| A transaction dated exactly on the call date | `call_date <= transaction.date` is inclusive by intent; untested |
| A debit whose amount is zero | I believe it is rejected by the zero rule before the sign rule, but the order is incidental, not designed |
| Thousands separators in a quoted field with surrounding spaces | Trim happens before validation per the brief; combined with `csv` padding I have not checked it |
| An empty file, or a header with only some of the five columns | "Missing column rejects the file" covers it, but a zero-row body is a different path |

The bug this already found is the reason to take the table seriously. During
Phase 6 the reference rule reused the **name** normaliser, which replaces
punctuation with spaces instead of deleting it. `CC-1002` in a description
normalised to `CC 1002`, so a hyphenated reference could never be found. The
sample file contains hyphenated references, and the app had been returning
`suggested` for those rows for hours without anyone noticing, because a partial
screenshot looked plausible. A single end-to-end assertion would have caught it
in one run.

---

## 3. Frontend

**Money is summed with `Number()` in two places** — `App.jsx:69` and
`App.jsx:73`, the funded and called totals in the summary strip. `formatMoney`
also passes its argument straight to `Intl.NumberFormat`, which coerces to a
float internally. All of it is display-only and never sent back to the server,
and the backend is the only place money is a `Decimal`, so nothing is corrupted
today. But it is the wrong direction: the correct fix is to have the server
compute the summary numbers and ship them as strings, which also removes two
`Number()` calls from the component. I left it because the alternative was
adding a summary endpoint under time pressure, and a display-only float is the
smaller risk of the two.

**One lint warning I chose not to silence:** `react(set-state-in-effect` at
the data-fetch effect in `App.jsx`. The rule is right in general — effects that
set state on mount are a smell — and this one is the exception, because the
alternative is fetching in an event handler that does not exist. If I rewrote
it I would move the fetch into a small `useOrganizations`/`useTransactions`
pair so the rule stops seeing a bare effect.

**No test of the frontend at all.** No component tests, no test of the
`pending` map that disables a button mid-request. I checked the disabled logic
by clicking it, which is not the same thing as a test that fails when the logic
breaks.

**No pagination.** `Meta.ordering` is set and the API returns everything. The
brief says files may contain a few thousand rows; a few thousand rendered table
rows in React is where the page starts to feel slow. See the next-steps list in
`ASSESSMENT_NOTES.md`.

**Accessibility is thinner than it should be.** The status badges are colour
plus text, so they are not colour-only, but I did not test the page with a
screen reader or walk the tab order. The row actions are real `<button>`
elements, which is the main thing, and I did not add focus management for the
post-action refetch, which may well matter.

---

## 4. Backend, smaller items

- **Import is not streaming.** The whole file is read and parsed into memory
  before anything is written. "A few thousand rows" is fine; a few hundred
  thousand would not be, and the brief only promises the former.
- **No index on `BankTransaction.date`.** Ordering is newest-first on an
  unindexed column. Fine at this size, and the first thing I would add with
  pagination.
- **Import holds one transaction for the whole file.** That is deliberate and
  I would keep it — partial imports with no way to tell what landed are worse
  than an all-or-nothing file — but it does mean a large file holds locks for
  its duration.
- **`Match.organization` is denormalized** from the transaction. It keeps the
  scoping pattern uniform across all six models, but it is a column that can
  disagree with its source if anything ever writes a `Match` directly instead
  of going through the service layer. Nothing does today.
- **The Airtable bonus is not built.** Optional, and I would rather spend the
  time on the tests in section 2.

---

## What I would do with one more day

1. Add the end-to-end sample-file test from section 2.
2. Write the adversarial CSV in section 3 and run it through the UI.
3. Move the summary totals to the server and delete both `Number()` calls.
4. Re-read `services.py` top to bottom without the intent that produced it,
   looking only for what a reviewer would attack first.
