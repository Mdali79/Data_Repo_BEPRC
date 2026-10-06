"""
Small helpers shared by every list/table view: pagination, sorting,
date parsing and "active filter" chips. Kept framework-light so the
same pattern works for any future table (other organizations' apps too).
"""

from datetime import date

from django.core.paginator import Paginator
from django.contrib import messages
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme

PER_PAGE_CHOICES = (10, 25, 50, 100)


def paginate(request, qs, default=25):
    try:
        per_page = int(request.GET.get("per_page", default))
    except (TypeError, ValueError):
        per_page = default
    if per_page not in PER_PAGE_CHOICES:
        per_page = default
    paginator = Paginator(qs, per_page)
    page = paginator.get_page(request.GET.get("page"))
    page.elided_range = list(paginator.get_elided_page_range(page.number, on_each_side=1, on_ends=1))
    page.per_page = per_page
    page.per_page_choices = PER_PAGE_CHOICES
    return page


def apply_sort(request, qs, allowed: dict, default: str):
    """
    allowed: {"public_key": "orm_field_or_expression"}; ?sort=key or ?sort=-key.
    Returns (qs, current_sort_key).
    """
    raw = request.GET.get("sort") or default
    key = raw.lstrip("-")
    if key not in allowed:
        raw, key = default, default.lstrip("-")
    field = allowed[key]
    desc = raw.startswith("-")
    if isinstance(field, str):
        order = [f"-{field}" if desc else field]
    else:  # tuple of fields, e.g. ("report_date", "hour")
        order = [f"-{f}" if desc else f for f in field]
    return qs.order_by(*order), raw


def parse_date(value):
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def chips(request, specs):
    """
    specs: list of (param, label, display_value_or_None). Returns
    [{"label", "value", "remove_url"}] for every param present in the query.
    """
    out = []
    for param, label, display in specs:
        value = request.GET.get(param)
        if not value:
            continue
        q = request.GET.copy()
        q.pop(param, None)
        q.pop("page", None)
        out.append({"label": label, "value": display if display is not None else value, "remove_url": "?" + q.urlencode()})
    return out


def ack(request, title, body="", level=messages.SUCCESS):
    """Acknowledgement shown as a modal after an action (title travels in extra_tags)."""
    messages.add_message(request, level, body or title, extra_tags=title)


def toast(request, body, level=messages.INFO):
    messages.add_message(request, level, body)


def safe_next(request, fallback):
    """Redirect to POST['next'] if it's a local URL (keeps list filters/page), else fallback."""
    nxt = request.POST.get("next")
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        return redirect(nxt)
    return redirect(fallback)
