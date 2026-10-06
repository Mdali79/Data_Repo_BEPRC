# BEPRC Data Platform — Phase 1 (NLDC domain)

Working scaffold for the pilot described in the BEPRC Data Dictionary &
Schema v1 doc: ingest Power Grid Bangladesh PLC / NLDC daily reports into
a standardized PostgreSQL schema, with full raw-file + cell-level lineage,
behind a login-gated web panel (signup/login/logout, upload, submission
status, two report pages with CSV/Excel export).

## Does file upload need to happen in a particular order?

No date order, and no cross-organization order — each report is keyed by
(organization, date, filename), and re-uploading the same date safely
replaces it rather than duplicating. There IS one dependency, and it's
handled automatically: within a single file, entity rows (a generating
unit, a substation) must exist before the readings that reference them.
`ingestion/services.py` enforces that ordering on every import via
`get_or_create()` — the person uploading never has to think about it.
The only manual step is resolving name spelling variants (e.g. "Ghorasal"
vs "Ghorashal") in the `PlantNameAlias` admin screen, which is a data
governance step, not a sequencing one.

## Status pipeline (what "sequence" means for the UI)

```
Upload  -->  Parse (automatic, same request)  -->  parsed / failed
                                                        |
                                          (optional admin review)
                                                        v
                                                    approved
```

Reports and exports only read submissions with status `parsed` or
`approved`, so a failed import never silently shows up in a chart. Bump a
submission to `approved` in the admin panel once someone's checked it;
until then `parsed` is good enough to appear in reports.

## What's here and what's proven

- `ingestion/parsers/nldc_daily_report.py` — pure-Python parsing logic
  (openpyxl only, no Django). **Already run against all 5 of your sample
  files** (10–14 Sep 2026) and verified correct: Forecast (151 units),
  GenLog (4,075 hourly readings), P1 system summary, P1 zone-generation
  (90 rows), P4 hourly (25 rows), Voltage (291 readings), En-Curve
  (705 readings). Run it yourself any time:
  ```
  python ingestion/parsers/nldc_daily_report.py path/to/Daily_Report_10-09-2026.xlsx
  ```
- `ingestion/models.py` — the ORM schema matching the data dictionary:
  `Organization`, `PowerPlant`/`GeneratingUnit`/`UnitGeneration`,
  `Substation`/`VoltageReading`, `SystemSummary`, `ZoneGeneration`,
  `SystemHourly`, `FuelSourceReading`, plus `ReportSubmission` and
  `StagingCell` for the raw/lineage layers.
- `ingestion/admin.py` — Django's built-in admin, used deliberately as
  the review UI: filter `ReportSubmission` by `status=needs_review`,
  resolve plant name variants (Ghorasal/Ghorashal) in `PlantNameAlias`.
- `ingestion/services.py` — `import_report()`, the ONE place parsed data
  is written to the ORM. Both the CLI command below and the web upload
  view call this — no duplicated logic to drift out of sync.
- `ingestion/management/commands/import_nldc_report.py` — CLI wrapper
  around `import_report()`, for bulk/scripted loading.
- `ingestion/management/commands/bootstrap.py` — creates the NLDC
  organization row so it exists before your first signup or import.
- `accounts/` — custom user model (`organization` + `role`: uploader /
  analyst / admin), signup/login/logout views and templates. Signup
  always creates an `uploader` for the chosen organization — nobody can
  self-grant analyst/admin (promote people in the Django admin).
- `ingestion/views.py` + `templates/` — the panel itself: upload form,
  submission list (filterable by status) and detail page, a dashboard,
  and two report pages (System Hourly, Plant Generation) each with a
  date-range filter and a CSV/Excel download button.

**Not yet run in this environment**: the Django/Postgres wiring itself.
The sandbox this was built in has no network access, so `pip install`
and a live Postgres server aren't available here — but the parsing logic
(the part with the real risk of bugs) is tested against your real files,
and the Django code follows well-established patterns. Run the steps
below on your own machine to bring the rest online.

## Setup

```bash
docker-compose up -d db
pip install -r requirements.txt   # or use the Docker web service
python manage.py migrate
python manage.py bootstrap          # creates the NLDC organization row
python manage.py createsuperuser    # your admin login for /admin/
python manage.py runserver
```

Then:

1. Visit `http://localhost:8000/admin/`, log in with the superuser, and
   set your own user's `role` to `admin` (Accounts → Users) so the panel
   nav shows the Admin link.
2. Visit `http://localhost:8000/` — log in, then **Upload** a
   `Daily_Report_DD-MM-YYYY.xlsx` file. You're redirected straight to the
   parsed submission.
3. Open **System hourly report** or **Plant generation report**, filter
   by date, and use the **Download CSV / Download Excel** buttons.
4. Try **Sign up** in a private/incognito window to see the self-service
   flow a real organization's uploader would use — they land as
   `uploader` for the org they picked, and only ever see that org's data.

Or skip the UI for bulk loading:
```bash
python manage.py import_nldc_report path/to/Daily_Report_10-09-2026.xlsx
```

## Why Django (over the FastAPI I first suggested)

Once the data dictionary showed how much of this platform is "staged
data waiting for human review and approval" — the exact workflow ChatGPT's
proposal also flagged — Django's free admin panel became the deciding
factor over FastAPI. It gives a working review/approve UI, auth, and an
ORM with zero extra build effort, which matters a lot for a one-person
team. A separate public-facing upload site (Phase 2, see below) can be a
thin Django view or a small API layer in front of the same models —
nothing here needs to change to support that.

## What's deliberately NOT built yet

- **Async parsing** (Celery/Redis) — upload parses synchronously, in the
  same request. Fine at this volume (GenLog's ~4,000 rows parse in well
  under a second); add a task queue if a future organization's files are
  much larger or parsing gets noticeably slow for the person uploading.
- **Forced approval workflow** — `approved` status exists and reports
  prefer it, but nothing currently blocks `parsed` data from appearing.
  Tighten `REPORT_STATUSES` in `ingestion/views.py` to `("approved",)`
  once you want every report gated on a human sign-off.
- **Password reset / email verification** — signup and login work;
  "forgot password" is Django's built-in `PasswordResetView`, not yet
  wired into `accounts/urls.py`.
- **P2, P3, L-Curve, EWIC parsers** — not implemented, but every pattern
  they'd need already exists in `nldc_daily_report.py` (per-plant table
  like Forecast/P2, paired zone blocks like P3, a 30-min curve like
  En-Curve/L-Curve). Extending is copy-adapt work, not new design.
- **IEPMP (or any other organization's) tables** — per the "any org,
  anytime" discussion: those get their own app (e.g. `iepmp/models.py`)
  with their own tables. Nothing in `ingestion/` should be edited to fit
  a different domain — only added alongside.

## Ground rules this scaffold follows (don't break these)

1. Never repurpose an existing table/column's meaning for a new domain —
   add a new table instead.
2. Only additive migrations on shared tables (`Organization`,
   `ReportSubmission`, `StagingCell`).
3. Keep domain-specific assumptions out of the shared/core models.
4. A new domain = a new Django app + new parser, never an edit to an
   existing one.
