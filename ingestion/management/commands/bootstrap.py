"""
One-shot setup for a fresh install:
    python manage.py bootstrap

Creates the NLDC organization (so it exists before the first import or
signup) and prints next-step commands. Does NOT create a superuser —
run `python manage.py createsuperuser` yourself so the password is never
in a script.
"""

from django.core.management.base import BaseCommand

from ingestion.models import Organization

NLDC_ORG_NAME = "Power Grid Bangladesh PLC / NLDC"


class Command(BaseCommand):
    help = "Create baseline reference data (organizations) for a fresh install."

    def handle(self, *args, **options):
        org, created = Organization.objects.get_or_create(
            name=NLDC_ORG_NAME, defaults={"short_name": "NLDC", "sector": "power"}
        )
        self.stdout.write(self.style.SUCCESS(
            f"{'Created' if created else 'Already existed'}: {org}"
        ))
        self.stdout.write("Next: python manage.py createsuperuser")
