from django.contrib import admin
from . import models


@admin.register(models.Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("short_name", "name", "sector")
    search_fields = ("name", "short_name")


@admin.register(models.ReportSubmission)
class ReportSubmissionAdmin(admin.ModelAdmin):
    list_display = ("organization", "report_date", "status", "uploaded_at")
    list_filter = ("status", "organization")
    readonly_fields = ("uploaded_at", "parsed_at")
    # This list is your "needs review" queue at a glance — filter by
    # status=needs_review to see everything a parser choked on.


@admin.register(models.PowerPlant)
class PowerPlantAdmin(admin.ModelAdmin):
    list_display = ("canonical_name", "organization")
    search_fields = ("canonical_name",)


@admin.register(models.PlantNameAlias)
class PlantNameAliasAdmin(admin.ModelAdmin):
    # This is where you resolve "Ghorasal" vs "Ghorashal" by hand for now —
    # add a row here whenever a parser encounters a new spelling variant.
    list_display = ("raw_name", "plant")
    search_fields = ("raw_name",)


@admin.register(models.GeneratingUnit)
class GeneratingUnitAdmin(admin.ModelAdmin):
    list_display = ("unit_name", "plant", "fuel_type", "producer_type")
    search_fields = ("unit_name",)
    list_filter = ("fuel_type", "producer_type")


@admin.register(models.UnitGeneration)
class UnitGenerationAdmin(admin.ModelAdmin):
    list_display = ("unit", "report_date", "hour", "reading_type", "generation_mw")
    list_filter = ("reading_type", "report_date")
    date_hierarchy = "report_date"


@admin.register(models.Substation)
class SubstationAdmin(admin.ModelAdmin):
    list_display = ("name", "voltage_level")


@admin.register(models.VoltageReading)
class VoltageReadingAdmin(admin.ModelAdmin):
    list_display = ("substation", "report_date", "max_voltage_kv", "min_voltage_kv")
    date_hierarchy = "report_date"


@admin.register(models.SystemSummary)
class SystemSummaryAdmin(admin.ModelAdmin):
    list_display = (
        "report_date", "evening_peak_generation_mw", "evening_peak_demand_mw",
        "energy_unserved_mkwh",
    )
    date_hierarchy = "report_date"


@admin.register(models.SystemHourly)
class SystemHourlyAdmin(admin.ModelAdmin):
    list_display = ("report_date", "hour", "generation_mw", "load_shed_mw", "demand_mw")
    date_hierarchy = "report_date"


@admin.register(models.FuelSourceReading)
class FuelSourceReadingAdmin(admin.ModelAdmin):
    list_display = ("report_date", "time", "source", "category", "value_mw")
    list_filter = ("category", "source")


admin.site.register(models.ZoneGeneration)
