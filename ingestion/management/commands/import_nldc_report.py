"""
Usage:
    python manage.py import_nldc_report path/to/Daily_Report_10-09-2026.xlsx

Thin CLI wrapper - all the actual logic lives in ingestion/services.py,
shared with the web upload view (see the note at the bottom of that file
on why there is exactly one import code path).
"""

import os

from django.core.management.base import BaseCommand, CommandError

from ingestion.models import Organization
from ingestion.services import import_report

NLDC_ORG_NAME = "Power Grid Bangladesh PLC / NLDC"


class Command(BaseCommand):
    help = "Parse an NLDC Daily Report workbook and load it into the standardized tables."

    def add_arguments(self, parser):
        parser.add_argument("path", type=str)

    def handle(self, *args, **options):
        path = options["path"]
        if not os.path.exists(path):
            raise CommandError(f"File not found: {path}")

        org, _ = Organization.objects.get_or_create(
            name=NLDC_ORG_NAME, defaults={"short_name": "NLDC", "sector": "power"}
        )

        result = import_report(path, org)
        if result.error:
            raise CommandError(f"Import failed: {result.error}")

        self.stdout.write(self.style.SUCCESS(
            f"Imported {path} -> submission #{result.submission.id} ({result.submission.report_date})"
        ))
