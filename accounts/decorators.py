from functools import wraps

from django.contrib.auth.decorators import login_required
from django.shortcuts import render


def _forbidden(request, message):
    return render(request, "403.html", {"message": message}, status=403)


def perm_required(code):
    """Login + a permission code from accounts/permissions.py."""
    def decorator(view):
        @login_required
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not request.user.has_perm_code(code):
                from .permissions import PERMISSION_LABELS
                return _forbidden(request, f"Your role doesn't include the permission “{PERMISSION_LABELS.get(code, code)}”.")
            return view(request, *args, **kwargs)
        return wrapped
    return decorator


def superuser_required(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_superuser:
            return _forbidden(request, "Only a super admin can manage users, roles and permissions.")
        return view(request, *args, **kwargs)
    return wrapped
