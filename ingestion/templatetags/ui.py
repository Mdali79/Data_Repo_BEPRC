from django import template
from django.template.loader import get_template
from django.utils.html import format_html

register = template.Library()


@register.simple_tag(takes_context=True)
def qs(context, **overrides):
    """Current query string with overrides. Value None/'' removes the key.
    Changing anything except `page` resets to page 1."""
    q = context["request"].GET.copy()
    if "page" not in overrides:
        q.pop("page", None)
    for k, v in overrides.items():
        if v is None or v == "":
            q.pop(k, None)
        else:
            q[k] = v
    s = q.urlencode()
    return "?" + s if s else "?"


@register.simple_tag(takes_context=True)
def sort_th(context, label, key, align=""):
    """Clickable, sortable table header."""
    current = context.get("sort") or ""
    active = current.lstrip("-") == key
    desc = current.startswith("-")
    if active:
        nxt = key if desc else "-" + key
    else:
        nxt = "-" + key if align == "r" else key  # numbers default to high-first
    arrow = ("↓" if desc else "↑") if active else "↕"
    url = qs(context, sort=nxt)
    return format_html(
        '<th class="sortable {}{}"><a href="{}">{}<span class="sort-ind">{}</span></a></th>',
        align, " sorted" if active else "", url, label, arrow,
    )


# NOTE: these render their partial with a fresh dict instead of being
# @inclusion_tag. Inclusion tags copy the template Context, and Django 5.0's
# Context.__copy__ crashes on Python 3.14 ("'super' object has no attribute
# 'dicts'"). Rendering the partial directly avoids the copy on any version.

def _render(name, data):
    return get_template(name).render(data)


@register.simple_tag(takes_context=True)
def pagination(context, page, noun="rows"):
    return _render("partials/pagination.html", {"page": page, "noun": noun, "request": context["request"]})


@register.simple_tag
def daterange(start="", end="", start_name="start", end_name="end", label="Date range"):
    return _render("partials/daterange.html", {
        "start": start or "", "end": end or "", "start_name": start_name, "end_name": end_name, "label": label,
    })


@register.simple_tag
def filter_chips(items, reset_url):
    return _render("partials/chips.html", {"items": items, "reset_url": reset_url})
