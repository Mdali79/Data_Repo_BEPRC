"""
Single entry point for turning an uploaded file into standardized rows.
Both `manage.py import_nldc_report` and the web upload view call
`import_report()` — there is exactly one implementation of "what happens
when a report comes in," which is the answer to "does upload have a
required sequence": see the note at the bottom of this file.
"""

import os

from django.core.files import File
from django.db import transaction
from django.utils import timezone

from .models import (
    Organization, ReportSubmission, GeneratingUnit, UnitGeneration,
    Substation, VoltageReading, SystemSummary, ZoneGeneration,
    SystemHourly, FuelSourceReading,
)
from .parsers.nldc_daily_report import parse_report


class ImportResult:
    def __init__(self, submission, created, error=None):
        self.submission = submission
        self.created = created
        self.error = error


def import_report(file_path: str, organization: Organization, django_file=None,
                  original_filename: str | None = None) -> ImportResult:
    """
    file_path: path readable on disk right now (for parsing).
    django_file: an already-open Django File/UploadedFile to attach as the
    stored original (pass this from the upload view; the management
    command instead opens file_path itself — see below).
    original_filename: the name the user uploaded. The upload view parses
    from a temp file (e.g. tmpab12cd.xlsx) whose name has no date in it,
    so it must pass the real name here — the report date comes from it.
    """
    original_filename = os.path.basename(original_filename or file_path)
    try:
        parsed = parse_report(file_path, source_name=original_filename)
    except Exception as exc:
        # Bad filename / not a Daily Report workbook / missing sheet:
        # report it back to the uploader instead of a 500 error page.
        return ImportResult(None, False, error=f"Could not read the file: {exc}")
    report_date = parsed["report_date"]

    with transaction.atomic():
        submission, created = ReportSubmission.objects.update_or_create(
            organization=organization,
            report_date=report_date,
            original_filename=original_filename,
            defaults={"status": "pending"},
        )
        if created:
            if django_file is not None:
                submission.file.save(original_filename, django_file, save=True)
            else:
                with open(file_path, "rb") as f:
                    submission.file.save(original_filename, File(f), save=True)
        else:
            # Re-upload of the same report: replace the old rows instead of
            # duplicating them (loaders below use plain create() for these).
            submission.unit_generation.all().delete()
            submission.zone_generation.all().delete()
            submission.fuel_source_readings.all().delete()

        try:
            # Savepoint: if a loader fails, roll back just its partial rows so
            # the "failed" status below can still be saved (on PostgreSQL an
            # error otherwise aborts the whole transaction).
            with transaction.atomic():
                _load_forecast(submission, parsed["forecast"], report_date)
                _load_genlog(submission, parsed["genlog"], report_date)
                _load_system_summary(submission, parsed["system_summary"], report_date)
                _load_zone_generation(submission, parsed["zone_generation"], report_date)
                _load_system_hourly(submission, parsed["system_hourly"], report_date)
                _load_voltage(submission, parsed["voltage"], report_date)
                _load_fuel_source(submission, parsed["fuel_source"], report_date)
        except Exception as exc:
            submission.status = "failed"
            submission.error_message = str(exc)
            submission.save()
            return ImportResult(submission, created, error=str(exc))

        submission.status = "parsed"
        submission.parsed_at = timezone.now()
        submission.save()

    return ImportResult(submission, created)


# -- loaders (unchanged logic, moved here from the management command) ----

def _get_unit(name, defaults):
    unit, _ = GeneratingUnit.objects.get_or_create(unit_name=name, defaults=defaults)
    return unit


def _load_forecast(submission, rows, report_date):
    for r in rows:
        unit = _get_unit(r["unit_name"], {
            "fuel_type": r["fuel_type"] or "",
            "producer_type": r["producer_type"] or "",
            "unit_capacity_spec": r["unit_capacity_spec"] or "",
        })
        common = dict(unit=unit, submission=submission, report_date=report_date,
                      installed_capacity_mw=r["installed_capacity_mw"],
                      present_capacity_mw=r["present_capacity_mw"],
                      remarks=r["remarks"] or "")
        UnitGeneration.objects.create(reading_type="actual_day_peak", generation_mw=r["actual_gen_day_peak_mw"], **common)
        UnitGeneration.objects.create(reading_type="actual_evening_peak", generation_mw=r["actual_gen_evening_peak_mw"], **common)
        UnitGeneration.objects.create(reading_type="forecast_day_peak", generation_mw=r["forecast_gen_day_peak_mw"], **common)
        UnitGeneration.objects.create(reading_type="forecast_evening_peak", generation_mw=r["forecast_gen_evening_peak_mw"], **common)
        UnitGeneration.objects.create(reading_type="effective_day_peak", generation_mw=r["effective_gen_day_peak_mw"], **common)
        UnitGeneration.objects.create(reading_type="effective_evening_peak", generation_mw=r["effective_gen_evening_peak_mw"], **common)


def _load_genlog(submission, rows, report_date):
    for r in rows:
        unit = _get_unit(r["unit_name"], {})
        UnitGeneration.objects.create(
            unit=unit, submission=submission, report_date=report_date,
            hour=r["hour"], reading_type="actual_hourly",
            generation_mw=r["generation_mw"],
            present_capacity_mw=r["present_capacity_mw"],
        )


def _load_system_summary(submission, s, report_date):
    s = dict(s)
    s.pop("report_date")
    SystemSummary.objects.update_or_create(
        report_date=report_date, defaults={"submission": submission, **s}
    )


def _load_zone_generation(submission, rows, report_date):
    for r in rows:
        ZoneGeneration.objects.create(submission=submission, **r)


def _load_system_hourly(submission, rows, report_date):
    for r in rows:
        SystemHourly.objects.update_or_create(
            report_date=r["report_date"], hour=r["hour"],
            defaults={"submission": submission, **{k: v for k, v in r.items() if k not in ("report_date", "hour")}},
        )


def _load_voltage(submission, rows, report_date):
    for r in rows:
        substation, _ = Substation.objects.get_or_create(
            name=r["substation_name"], defaults={"voltage_level": r["voltage_level"] or ""}
        )
        VoltageReading.objects.update_or_create(
            substation=substation, report_date=report_date,
            defaults={
                "submission": submission,
                "max_voltage_kv": r["max_voltage_kv"],
                "max_voltage_time": r["max_voltage_time"],
                "min_voltage_kv": r["min_voltage_kv"],
                "min_voltage_time": r["min_voltage_time"],
            },
        )


def _load_fuel_source(submission, rows, report_date):
    for r in rows:
        FuelSourceReading.objects.create(submission=submission, **r)


# ---------------------------------------------------------------------------
# On "does upload have a required sequence?"
#
# No date-order dependency: `ReportSubmission` is keyed on
# (organization, report_date, filename), and every loader here uses
# get_or_create / update_or_create — so importing 14-Sep before 10-Sep,
# or re-importing the same file twice, produces the same end state.
#
# There IS a within-file dependency, handled automatically: entity rows
# (GeneratingUnit, Substation) must exist before the readings that
# reference them. get_or_create() enforces that ordering inside this
# function on every call — the person uploading never has to think about
# it. The one thing that stays manual is resolving name variants
# (Ghorasal vs Ghorashal creating two GeneratingUnit rows instead of one)
# via PlantNameAlias in the admin — see the "Upload -> Parse -> Review"
# pipeline in the README.
# ---------------------------------------------------------------------------
