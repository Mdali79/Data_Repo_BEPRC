"""
Canonical schema for the BEPRC data platform — NLDC domain (Phase 1).

This mirrors the "BEPRC Data Dictionary & Schema v1" doc: organizations at
the top, then entity tables (plants/units/substations), then reading
tables that reference those entities by FK rather than by free-text name.
The three-layer lineage (raw file -> staging cell -> standardized row) is
kept: `ReportSubmission` + `SourceSheet` hold the raw/staging side,
everything below is the standardized side.

Per the "any org, anytime" ground rules discussed: this app only ever
writes to ITS OWN tables. A future IEPMP (or any other org's) domain gets
its own Django app (e.g. `iepmp/models.py`) with its own tables — nothing
here gets renamed or repurposed to fit a different domain. Shared/core
concepts (Organization, ReportSubmission) stay generic and additive only.
"""

from django.db import models


# ---------------------------------------------------------------------------
# Core / shared across every organization and domain
# ---------------------------------------------------------------------------

class Organization(models.Model):
    name = models.CharField(max_length=255, unique=True)
    short_name = models.CharField(max_length=50, blank=True)
    sector = models.CharField(
        max_length=20,
        choices=[("energy", "Energy"), ("power", "Power")],
        default="power",
    )

    def __str__(self):
        return self.short_name or self.name


class ReportSubmission(models.Model):
    """One uploaded file. Raw file + parse status live here."""

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("parsed", "Parsed"),
        ("needs_review", "Needs review"),
        ("approved", "Approved"),
        ("failed", "Failed"),
    ]

    organization = models.ForeignKey(Organization, on_delete=models.PROTECT)
    report_date = models.DateField()
    original_filename = models.CharField(max_length=255)
    file = models.FileField(upload_to="raw_reports/%Y/%m/")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    parsed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        unique_together = ("organization", "report_date", "original_filename")

    def __str__(self):
        return f"{self.organization} — {self.report_date} ({self.status})"


class StagingCell(models.Model):
    """
    Cell-level lineage: every standardized value can be traced back to the
    exact sheet/row/column it came from. Populated by the parser alongside
    (not instead of) the standardized rows below.
    """

    submission = models.ForeignKey(ReportSubmission, on_delete=models.CASCADE, related_name="staging_cells")
    sheet_name = models.CharField(max_length=100)
    row_number = models.IntegerField()
    column_name = models.CharField(max_length=255)
    raw_value = models.TextField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["submission", "sheet_name"])]


# ---------------------------------------------------------------------------
# Entities — power plants, generating units, substations
# ---------------------------------------------------------------------------

class PowerPlant(models.Model):
    """Canonical plant identity — resolves name variants like Ghorasal/Ghorashal."""

    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, null=True, blank=True)
    canonical_name = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.canonical_name


class PlantNameAlias(models.Model):
    """Master-data lookup: maps a raw name seen in a source file to a canonical plant."""

    plant = models.ForeignKey(PowerPlant, on_delete=models.CASCADE, related_name="aliases")
    raw_name = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return f"{self.raw_name} -> {self.plant.canonical_name}"


class GeneratingUnit(models.Model):
    plant = models.ForeignKey(PowerPlant, on_delete=models.CASCADE, related_name="units", null=True, blank=True)
    unit_name = models.CharField(max_length=255, unique=True)
    fuel_type = models.CharField(max_length=50, blank=True)
    producer_type = models.CharField(max_length=50, blank=True)
    unit_capacity_spec = models.CharField(max_length=100, blank=True)  # e.g. "1*260"

    def __str__(self):
        return self.unit_name


class UnitGeneration(models.Model):
    """
    One reading of a generating unit at a point in time. `reading_type`
    disambiguates the several kinds of "generation" the source sheets
    report (Forecast has 3 flavours, GenLog is hourly actuals, P2 is peak
    + daily energy).
    """

    READING_TYPES = [
        ("actual_hourly", "Actual (hourly, GenLog)"),
        ("actual_day_peak", "Actual — day peak (prior day)"),
        ("actual_evening_peak", "Actual — evening peak (prior day)"),
        ("forecast_day_peak", "Forecast — day peak"),
        ("forecast_evening_peak", "Forecast — evening peak"),
        ("effective_day_peak", "Effective available — day peak"),
        ("effective_evening_peak", "Effective available — evening peak"),
        ("peak_hour", "Peak hour generation (P2)"),
        ("energy_generated_kwh", "Energy generated, day-long (P2)"),
    ]

    unit = models.ForeignKey(GeneratingUnit, on_delete=models.CASCADE, related_name="readings")
    submission = models.ForeignKey(ReportSubmission, on_delete=models.CASCADE, related_name="unit_generation")
    report_date = models.DateField()
    hour = models.TimeField(null=True, blank=True)
    reading_type = models.CharField(max_length=30, choices=READING_TYPES)
    generation_mw = models.FloatField(null=True, blank=True)
    installed_capacity_mw = models.FloatField(null=True, blank=True)
    present_capacity_mw = models.FloatField(null=True, blank=True)
    remarks = models.CharField(max_length=255, blank=True)

    class Meta:
        indexes = [models.Index(fields=["unit", "report_date", "reading_type"])]


class Substation(models.Model):
    name = models.CharField(max_length=255, unique=True)
    voltage_level = models.CharField(max_length=20, blank=True)  # e.g. "400 kV"

    def __str__(self):
        return self.name


class VoltageReading(models.Model):
    substation = models.ForeignKey(Substation, on_delete=models.CASCADE, related_name="readings")
    submission = models.ForeignKey(ReportSubmission, on_delete=models.CASCADE, related_name="voltage_readings")
    report_date = models.DateField()
    max_voltage_kv = models.FloatField(null=True, blank=True)
    max_voltage_time = models.TimeField(null=True, blank=True)
    min_voltage_kv = models.FloatField(null=True, blank=True)
    min_voltage_time = models.TimeField(null=True, blank=True)

    class Meta:
        unique_together = ("substation", "report_date")


# ---------------------------------------------------------------------------
# System-wide daily/hourly readings (P1, P4, En-Curve)
# ---------------------------------------------------------------------------

class SystemSummary(models.Model):
    """One row per daily report (P1 sheet)."""

    submission = models.OneToOneField(ReportSubmission, on_delete=models.CASCADE, related_name="system_summary")
    report_date = models.DateField(unique=True)
    day_peak_generation_mw = models.FloatField(null=True, blank=True)
    day_peak_generation_time = models.TimeField(null=True, blank=True)
    day_peak_demand_mw = models.FloatField(null=True, blank=True)
    day_peak_demand_time = models.TimeField(null=True, blank=True)
    evening_peak_generation_mw = models.FloatField(null=True, blank=True)
    evening_peak_generation_time = models.TimeField(null=True, blank=True)
    evening_peak_demand_mw = models.FloatField(null=True, blank=True)
    evening_peak_demand_time = models.TimeField(null=True, blank=True)
    min_generation_mw = models.FloatField(null=True, blank=True)
    min_generation_time = models.TimeField(null=True, blank=True)
    max_generation_mw = models.FloatField(null=True, blank=True)
    max_generation_time = models.TimeField(null=True, blank=True)
    energy_generated_mkwh = models.FloatField(null=True, blank=True)
    energy_unserved_mkwh = models.FloatField(null=True, blank=True)
    energy_demand_mkwh = models.FloatField(null=True, blank=True)
    max_temperature_c = models.FloatField(null=True, blank=True)
    total_gas_supplied_mmcfd = models.FloatField(null=True, blank=True)
    production_cost_per_kwh_tk = models.FloatField(null=True, blank=True)


class ZoneGeneration(models.Model):
    """Zone-wise generation-by-fuel breakdown, part of P1."""

    submission = models.ForeignKey(ReportSubmission, on_delete=models.CASCADE, related_name="zone_generation")
    report_date = models.DateField()
    zone = models.CharField(max_length=100)
    fuel = models.CharField(max_length=50)
    energy_mkwh = models.FloatField(null=True, blank=True)


class SystemHourly(models.Model):
    """P4 sheet: system-wide generation/load-shed/demand, one row per hour."""

    submission = models.ForeignKey(ReportSubmission, on_delete=models.CASCADE, related_name="system_hourly")
    report_date = models.DateField()
    hour = models.TimeField()
    generation_mw = models.FloatField(null=True, blank=True)
    load_shed_mw = models.FloatField(null=True, blank=True)
    demand_mw = models.FloatField(null=True, blank=True)

    class Meta:
        unique_together = ("report_date", "hour")


class FuelSourceReading(models.Model):
    """En-Curve sheet: 30-minute generation by fuel/import source."""

    CATEGORY_CHOICES = [
        ("domestic_generation", "Domestic generation"),
        ("imported_power", "Imported power"),
        ("shortage", "Shortage"),
    ]

    submission = models.ForeignKey(ReportSubmission, on_delete=models.CASCADE, related_name="fuel_source_readings")
    report_date = models.DateField()
    time = models.CharField(max_length=5)  # "HH:MM" — 30-min slots, kept as text for simplicity
    source = models.CharField(max_length=50)
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES)
    value_mw = models.FloatField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["report_date", "source"])]
