# recon

A bank reconciliation tool for fund administrators. A GP imports a bank
statement CSV; the system suggests which capital call line item each incoming
payment belongs to, explains why, and updates funded amounts when a suggestion
is approved.

Django + DRF + PostgreSQL on the backend, a React SPA on the front. Setup
instructions and the full design rationale are in `ASSESSMENT_NOTES.md`.

```bash
python manage.py migrate
python manage.py seed_demo
python manage.py runserver        # :8000

cd frontend && npm install && npm run dev    # :5173
```

Tests: `python manage.py test`

## Two trade-offs I made

**`organization_from` stayed a helper function instead of becoming a DRF
mixin.** With seven endpoints the abstraction would have cost `self.request`
indirection and a class declaration to save one line in each view. The
scoped-existence check is one `filter(...).exists()` per action endpoint, and
it is visible rather than inherited. If the endpoint count grew into the
dozens I would revisit it.

**Matching uses the remaining balance as stored at import time, and only
approval re-checks it.** Re-checking during matching would mean a payment's
suggestion depended on how many other payments happened to be imported before
it, which makes the same file produce different suggestions depending on
upload order. Deferring the check to approval keeps matching deterministic and
puts the one authoritative check next to the write it protects.