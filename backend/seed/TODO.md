# Seed — TODO

## run_batch.py: dynamic time range from DB

Currently `DATA_START` and `DATA_END` are hardcoded in `run_batch.py`. This breaks if a developer generates their own `signals_seed.json` with a different date range.

**Fix:** replace the two constants with a DB query at the start of `main()`:

```python
cur.execute("SELECT MIN(record_date), MAX(record_date) FROM signals WHERE record_date IS NOT NULL")
DATA_START, DATA_END = cur.fetchone()
```

`_pg_connect()` is already available — no new dependency needed. This also handles the case where `import.py` is run multiple times with different source files.
