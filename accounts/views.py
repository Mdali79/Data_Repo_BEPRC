from django.contrib import messages
from django.contrib.auth import login
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from ingestion.models import Organization
from ingestion.utils import ack, apply_sort, chips, paginate, safe_next
from .decorators import superuser_required
from .forms import RoleForm, SignUpForm, UserCreateForm, UserEditForm
from .models import Role, User
from .permissions import PERMISSION_GROUPS


def signup_view(request):
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)  # sign them in immediately after signup
            ack(request, "Account created", f"Welcome, {user.username}! You're signed in as {user.get_role_display()} for {user.organization}.")
            return redirect("dashboard")
    else:
        form = SignUpForm()
    return render(request, "registration/signup.html", {"form": form})


# ---------------------------------------------------------------------------
# Super admin: users
# ---------------------------------------------------------------------------

@superuser_required
def user_list_view(request):
    qs = User.objects.select_related("organization")
    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(username__icontains=q) | Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q))
    role = request.GET.get("role") or ""
    if role == "__super":
        qs = qs.filter(is_superuser=True)
    elif role:
        qs = qs.filter(role=role, is_superuser=False)
    org = request.GET.get("org") or ""
    if org == "__none":
        qs = qs.filter(organization__isnull=True)
    elif org:
        qs = qs.filter(organization_id=org)
    status = request.GET.get("status") or ""
    if status == "active":
        qs = qs.filter(is_active=True)
    elif status == "inactive":
        qs = qs.filter(is_active=False)

    qs, sort = apply_sort(request, qs, {
        "username": "username", "email": "email", "role": "role", "org": "organization__name",
        "joined": "date_joined", "login": "last_login",
    }, "username")
    page = paginate(request, qs)
    roles = list(Role.objects.order_by("name"))
    orgs = list(Organization.objects.order_by("name"))
    role_names = {r.slug: r.name for r in roles} | {"__super": "Super admin"}
    org_names = {str(o.pk): str(o) for o in orgs} | {"__none": "No organization"}
    return render(request, "accounts/user_list.html", {
        "page": page, "sort": sort, "q": q, "roles": roles, "orgs": orgs,
        "current_role": role, "current_org": org, "current_status": status,
        "total": User.objects.count(),
        "chips": chips(request, [
            ("q", "Search", None), ("role", "Role", role_names.get(role)),
            ("org", "Organization", org_names.get(org)), ("status", "Status", status.title() if status else None),
        ]),
    })


@superuser_required
def user_create_view(request):
    form = UserCreateForm(request.POST or None, acting_user=request.user)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        ack(request, "User created", f"{user.username} can now log in as {user.get_role_display()}.")
        return redirect("user_list")
    return render(request, "accounts/user_form.html", {"form": form, "creating": True})


@superuser_required
def user_edit_view(request, pk):
    target = get_object_or_404(User, pk=pk)
    form = UserEditForm(request.POST or None, instance=target, acting_user=request.user)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        extra = " Their password was changed." if form.cleaned_data.get("new_password1") else ""
        ack(request, "User updated", f"Changes to {user.username} were saved.{extra}")
        return redirect("user_list")
    return render(request, "accounts/user_form.html", {"form": form, "creating": False, "target": target})


@require_POST
@superuser_required
def user_toggle_active_view(request, pk):
    target = get_object_or_404(User, pk=pk)
    if target.pk == request.user.pk:
        ack(request, "Not allowed", "You can't deactivate your own account.", messages.ERROR)
    else:
        target.is_active = not target.is_active
        target.save(update_fields=["is_active"])
        if target.is_active:
            ack(request, "User activated", f"{target.username} can log in again.")
        else:
            ack(request, "User deactivated", f"{target.username} can no longer log in. Their data is kept.")
    return safe_next(request, "/accounts/manage/users/")


@require_POST
@superuser_required
def user_delete_view(request, pk):
    target = get_object_or_404(User, pk=pk)
    if target.pk == request.user.pk:
        ack(request, "Not allowed", "You can't delete your own account.", messages.ERROR)
    elif target.is_superuser and User.objects.filter(is_superuser=True, is_active=True).count() <= 1:
        ack(request, "Not allowed", "This is the last active super admin.", messages.ERROR)
    else:
        name = target.username
        target.delete()
        ack(request, "User deleted", f"{name} was permanently removed.")
    return safe_next(request, "/accounts/manage/users/")


# ---------------------------------------------------------------------------
# Super admin: roles & permissions
# ---------------------------------------------------------------------------

@superuser_required
def role_list_view(request):
    user_counts = dict(User.objects.filter(is_superuser=False).values_list("role").annotate(n=Count("id")))
    roles = list(Role.objects.order_by("name"))
    for r in roles:
        r.user_count = user_counts.get(r.slug, 0)
        r.perm_set = set(r.permissions)
    return render(request, "accounts/role_list.html", {
        "roles": roles, "groups": PERMISSION_GROUPS,
        "superusers": User.objects.filter(is_superuser=True).count(),
    })


@superuser_required
def role_edit_view(request, pk=None):
    role = get_object_or_404(Role, pk=pk) if pk else None
    form = RoleForm(request.POST or None, instance=role)
    if request.method == "POST" and form.is_valid():
        saved = form.save()
        ack(request, "Role saved" if role else "Role created",
            f"“{saved.name}” now grants {len(saved.permissions)} permission{'s' if len(saved.permissions) != 1 else ''}. "
            "Users with this role get the change on their next page load.")
        return redirect("role_list")
    users = User.objects.filter(role=role.slug, is_superuser=False).count() if role else 0
    return render(request, "accounts/role_form.html", {"form": form, "role": role, "groups": PERMISSION_GROUPS, "users": users})


@require_POST
@superuser_required
def role_delete_view(request, pk):
    role = get_object_or_404(Role, pk=pk)
    n = User.objects.filter(role=role.slug).count()
    if role.is_system:
        ack(request, "Not allowed", f"“{role.name}” is a built-in role. You can edit its permissions, but not delete it.", messages.ERROR)
    elif n:
        ack(request, "Role is in use", f"{n} user{'s' if n != 1 else ''} still ha{'ve' if n != 1 else 's'} the “{role.name}” role. Move them to another role first.", messages.ERROR)
    else:
        name = role.name
        role.delete()
        ack(request, "Role deleted", f"“{name}” was removed.")
    return redirect("role_list")
