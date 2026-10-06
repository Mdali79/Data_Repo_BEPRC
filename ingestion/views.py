"""
Panel views. Every view is gated by a permission code from
accounts/permissions.py (see `perm_required`). Which roles hold which
permission is configured by a super admin at /accounts/manage/roles/.

Organization scoping: users without `view_all_orgs` only see their own
organization's submissions — enforced in `_scope_submissions`, the one
place that rule lives.
"""

import csv
import io
import os
import tempfile

from django.contrib import messages
from django.db.models import Avg, Count, F, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from accounts.decorators import perm_required
from .forms import UploadForm
from .models import (
    GeneratingUnit, ReportSubmission, SystemSummary, SystemHourly, UnitGeneration, Organization,
)
from .services import import_report
from .utils import ack, apply_sort, chips, paginate, parse_date, safe_next

REPORT_STATUSES = ("parsed", "approved")  # only trust reviewed-enough data in reports
HOURS = [f"{h:02d}:00" for h in range(24)]


def _scope_submissions(user, qs):
    if user.has_perm_code("view_all_orgs"):
        return qs
    return qs.filter(organization_id=user.organization_id)


def _date_range(request, qs, field="report_date"):
    start, end = parse_date(request.GET.get("start")), parse_date(request.GET.get("end"))
    if start:
        qs = qs.filter(**{f"{field}__gte": start})
    if end:
        qs = qs.filter(**{f"{field}__lte": end})
    return qs, start, end


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

@perm_required("upload_reports")
def upload_view(request):
    if request.method == "POST":
        form = UploadForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            org = form.get_organization()
            if org is None:
                form.add_error(None, "Your account has no organization set — ask a super admin to assign one.")
            else:
                uploaded = form.cleaned_data["file"]
                # The parser reads from a real path on disk, so stream the
                # upload to a temp file first; the original name is passed
                # separately because the report date is read from it.
                with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
                    for chunk in uploaded.chunks():
                        tmp.write(chunk)
                    tmp_path = tmp.name
                uploaded.seek(0)
                try:
                    result = import_report(tmp_path, org, django_file=uploaded, original_filename=uploaded.name)
                finally:
                    os.unlink(tmp_path)

                if result.error and result.submission is None:
                    form.add_error(None, result.error)
                    ack(request, "Upload failed", result.error, messages.ERROR)
                elif result.error:
                    ack(request, "Uploaded, but parsing failed", result.error, messages.ERROR)
                    return redirect("submission_detail", pk=result.submission.pk)
                else:
                    s = result.submission
                    verb = "uploaded and parsed" if result.created else "re-uploaded — the earlier data for this day was replaced"
                    ack(request, "Report uploaded", f"{s.original_filename} ({s.report_date:%d %b %Y}) was {verb}.")
                    return redirect("submission_detail", pk=s.pk)
    else:
        form = UploadForm(user=request.user)
    return render(request, "ingestion/upload.html", {"form": form})


# ---------------------------------------------------------------------------
# Submissions (status pipeline: pending -> parsed/failed -> needs_review -> approved)
# ---------------------------------------------------------------------------

@perm_required("view_submissions")
def submission_list_view(request):
    base = _scope_submissions(request.user, ReportSubmission.objects.select_related("organization"))
    qs = base

    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(original_filename__icontains=q) | Q(organization__name__icontains=q) | Q(organization__short_name__icontains=q))
    org_id = request.GET.get("org") or ""
    orgs = list(Organization.objects.order_by("name")) if request.user.has_perm_code("view_all_orgs") else []
    if org_id and orgs:
        qs = qs.filter(organization_id=org_id)
    qs, start, end = _date_range(request, qs)

    # Counts for the status tabs reflect every other filter.
    status_counts = dict(qs.order_by().values_list("status").annotate(n=Count("id")))
    status = request.GET.get("status") or ""
    if status:
        qs = qs.filter(status=status)

    qs, sort = apply_sort(request, qs, {
        "date": "report_date", "uploaded": "uploaded_at", "status": "status",
        "org": "organization__name", "file": "original_filename",
    }, "-date")
    page = paginate(request, qs)

    status_map = dict(ReportSubmission.STATUS_CHOICES)
    org_name = next((str(o) for o in orgs if str(o.pk) == org_id), None)
    return render(request, "ingestion/submission_list.html", {
        "page": page, "sort": sort, "q": q,
        "start": request.GET.get("start", ""), "end": request.GET.get("end", ""),
        "status_choices": [(v, l, status_counts.get(v, 0)) for v, l in ReportSubmission.STATUS_CHOICES],
        "current_status": status, "all_count": sum(status_counts.values()),
        "orgs": orgs, "current_org": org_id,
        "chips": chips(request, [
            ("q", "Search", None),
            ("status", "Status", status_map.get(status)),
            ("org", "Organization", org_name),
            ("start", "From", start and f"{start:%d %b %Y}"),
            ("end", "To", end and f"{end:%d %b %Y}"),
        ]),
    })


@perm_required("view_submissions")
def submission_detail_view(request, pk):
    submission = get_object_or_404(
        _scope_submissions(request.user, ReportSubmission.objects.select_related("organization")), pk=pk
    )
    summary = SystemSummary.objects.filter(report_date=submission.report_date).first()
    unit_count = UnitGeneration.objects.filter(submission=submission).values("unit").distinct().count()
    hourly_count = SystemHourly.objects.filter(submission=submission).count()
    return render(request, "ingestion/submission_detail.html", {
        "submission": submission,
        "summary": summary,
        "unit_count": unit_count,
        "hourly_count": hourly_count,
    })


@require_POST
@perm_required("review_submissions")
def submission_status_view(request, pk):
    submission = get_object_or_404(_scope_submissions(request.user, ReportSubmission.objects.all()), pk=pk)
    new_status = request.POST.get("status")
    if submission.status == "failed":
        ack(request, "Status not changed", "A failed submission can't be reviewed — fix the file and upload it again.", messages.ERROR)
    elif new_status not in {"approved", "needs_review", "parsed"}:
        ack(request, "Status not changed", "Unknown status.", messages.ERROR)
    else:
        submission.status = new_status
        submission.save(update_fields=["status"])
        ack(request, "Status updated", f"The report for {submission.report_date:%d %b %Y} is now “{submission.get_status_display()}”.")
    return safe_next(request, reverse("submission_detail", args=[pk]))


@require_POST
@perm_required("delete_submissions")
def submission_delete_view(request, pk):
    submission = get_object_or_404(_scope_submissions(request.user, ReportSubmission.objects.all()), pk=pk)
    label = f"{submission.original_filename} ({submission.report_date:%d %b %Y})"
    if submission.file:
        submission.file.delete(save=False)
    submission.delete()  # parsed rows cascade with it
    ack(request, "Submission deleted", f"{label} and all data parsed from it were removed.")
    return safe_next(request, reverse("submission_list"))


# ---------------------------------------------------------------------------
# Dashboard / reports
# ---------------------------------------------------------------------------

@perm_required("view_dashboard")
def dashboard_view(request):
    # Last 30 report days, oldest -> newest for the trend chart.
    summaries = list(
        SystemSummary.objects.filter(submission__status__in=REPORT_STATUSES)
        .order_by("-report_date")[:30]
    )[::-1]
    latest = summaries[-1] if summaries else None

    subs = _scope_submissions(request.user, ReportSubmission.objects.select_related("organization"))
    status_counts = dict(subs.order_by().values_list("status").annotate(n=Count("id")))

    return render(request, "ingestion/dashboard.html", {
        "summaries": summaries,
        "latest": latest,
        "recent_submissions": subs.order_by("-uploaded_at")[:6],
        "total_submissions": sum(status_counts.values()),
        "ok_submissions": status_counts.get("parsed", 0) + status_counts.get("approved", 0),
        "failed_submissions": status_counts.get("failed", 0),
    })


def _hourly_qs(request):
    qs = SystemHourly.objects.filter(submission__status__in=REPORT_STATUSES)
    qs, start, end = _date_range(request, qs)
    h_from, h_to = request.GET.get("hour_from"), request.GET.get("hour_to")
    if h_from in HOURS:
        qs = qs.filter(hour__gte=h_from)
    if h_to in HOURS:
        qs = qs.filter(hour__lte=h_to)
    if request.GET.get("shed") == "1":
        qs = qs.filter(load_shed_mw__gt=0)
    return qs, start, end


@perm_required("view_reports")
def report_system_hourly_view(request):
    qs, start, end = _hourly_qs(request)
    chart_rows = list(qs.order_by("report_date", "hour")[:2000])  # chart: whole filtered range (capped)
    table_qs, sort = apply_sort(request, qs, {
        "time": ("report_date", "hour"), "gen": "generation_mw", "shed": "load_shed_mw", "demand": "demand_mw",
    }, "time")
    page = paginate(request, table_qs, default=25)
    return render(request, "ingestion/report_system_hourly.html", {
        "rows": chart_rows, "page": page, "sort": sort, "hours": HOURS,
        "start": request.GET.get("start", ""), "end": request.GET.get("end", ""),
        "hour_from": request.GET.get("hour_from", ""), "hour_to": request.GET.get("hour_to", ""),
        "shed": request.GET.get("shed", ""),
        "chips": chips(request, [
            ("start", "From", start and f"{start:%d %b %Y}"),
            ("end", "To", end and f"{end:%d %b %Y}"),
            ("hour_from", "Hour from", None), ("hour_to", "Hour to", None),
            ("shed", "Only", "hours with load-shed"),
        ]),
    })


def _plant_qs(request):
    qs = UnitGeneration.objects.filter(reading_type="actual_hourly", submission__status__in=REPORT_STATUSES)
    qs, start, end = _date_range(request, qs)
    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(unit__unit_name__icontains=q)
    fuel = request.GET.get("fuel") or ""
    if fuel:
        qs = qs.filter(unit__fuel_type=fuel)
    if request.GET.get("totals") != "1":
        # GenLog has "National Grid Total" / "Eastern Total" columns — not plants.
        qs = qs.exclude(unit__unit_name__iendswith="total")
    rows = qs.values("unit__unit_name", "unit__fuel_type").annotate(
        avg_generation_mw=Avg("generation_mw"), readings=Count("id"),
    )
    return rows, start, end


@perm_required("view_reports")
def report_plant_generation_view(request):
    rows, start, end = _plant_qs(request)
    rows, sort = apply_sort(request, rows, {
        "unit": "unit__unit_name", "fuel": "unit__fuel_type", "avg": "avg_generation_mw", "readings": "readings",
    }, "-avg")
    if sort.lstrip("-") == "avg":  # keep units with no readings at the bottom either way
        f = F("avg_generation_mw")
        rows = rows.order_by(f.desc(nulls_last=True) if sort.startswith("-") else f.asc(nulls_last=True))
    top = max((r["avg_generation_mw"] or 0 for r in rows), default=0)
    page = paginate(request, rows, default=25)
    fuels = (
        GeneratingUnit.objects.exclude(fuel_type="")
        .values_list("fuel_type", flat=True).distinct().order_by("fuel_type")
    )
    return render(request, "ingestion/report_plant_generation.html", {
        "page": page, "sort": sort, "top": top, "fuels": fuels,
        "start": request.GET.get("start", ""), "end": request.GET.get("end", ""),
        "q": request.GET.get("q", ""), "fuel": request.GET.get("fuel", ""), "totals": request.GET.get("totals", ""),
        "chips": chips(request, [
            ("q", "Unit", None), ("fuel", "Fuel", None),
            ("start", "From", start and f"{start:%d %b %Y}"),
            ("end", "To", end and f"{end:%d %b %Y}"),
            ("totals", "Including", "total rows"),
        ]),
    })


# ---------------------------------------------------------------------------
# Exports (same filters as the on-screen reports)
# ---------------------------------------------------------------------------

@perm_required("export_data")
def export_system_hourly_csv(request):
    qs, _, _ = _hourly_qs(request)
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="system_hourly.csv"'
    writer = csv.writer(response)
    writer.writerow(["report_date", "hour", "generation_mw", "load_shed_mw", "demand_mw"])
    for r in qs.order_by("report_date", "hour").iterator():
        writer.writerow([r.report_date, r.hour, r.generation_mw, r.load_shed_mw, r.demand_mw])
    return response


@perm_required("export_data")
def export_plant_generation_xlsx(request):
    import openpyxl
    from openpyxl.utils import get_column_letter

    rows, _, _ = _plant_qs(request)
    rows = rows.order_by(F("avg_generation_mw").desc(nulls_last=True))

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Plant Generation"
    headers = ["Unit", "Fuel", "Avg Generation (MW)", "Hourly readings"]
    ws.append(headers)
    for r in rows:
        ws.append([r["unit__unit_name"], r["unit__fuel_type"], r["avg_generation_mw"], r["readings"]])
    for i, _ in enumerate(headers, start=1):
        ws.column_dimensions[get_column_letter(i)].width = 28

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    response = HttpResponse(
        buf.read(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = 'attachment; filename="plant_generation.xlsx"'
    return response
