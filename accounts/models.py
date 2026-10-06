"""
Custom user model + configurable roles.

Access control:
- Every user has one Role (User.role stores the Role's slug).
- A Role is a named set of permission codes from accounts/permissions.py.
- Superusers have every permission and are the ONLY accounts that can
  create/edit users and roles (screens under /accounts/manage/).
- Uploaders/analysts without the `view_all_orgs` permission see only
  their own organization's submissions.
"""

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.functional import cached_property

from .permissions import ALL_PERMISSIONS, PERMISSION_LABELS


class Role(models.Model):
    slug = models.SlugField(max_length=50, unique=True, help_text="Internal key; cannot be changed after creation.")
    name = models.CharField(max_length=100, unique=True)
    description = models.CharField(max_length=255, blank=True)
    permissions = models.JSONField(default=list, blank=True)
    is_system = models.BooleanField(default=False, help_text="Built-in roles can be edited but not deleted.")
    is_default = models.BooleanField(default=False, help_text="Given to people who sign up themselves.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def permission_labels(self):
        return [PERMISSION_LABELS[p] for p in self.permissions if p in PERMISSION_LABELS]

    @classmethod
    def default_slug(cls):
        role = cls.objects.filter(is_default=True).first() or cls.objects.filter(slug="uploader").first()
        return role.slug if role else "uploader"


class _Can:
    """Template helper: {% if user.can.upload_reports %}."""

    def __init__(self, codes):
        self._codes = codes

    def __getitem__(self, code):
        return code in self._codes

    def __contains__(self, code):
        return code in self._codes


class User(AbstractUser):
    organization = models.ForeignKey(
        "ingestion.Organization",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users",
        help_text="Users without 'see all organizations' see only this organization's submissions.",
    )
    role = models.CharField(max_length=50, default="uploader", help_text="Slug of the user's Role.")

    @cached_property
    def role_obj(self):
        return Role.objects.filter(slug=self.role).first()

    def get_role_display(self):
        if self.is_superuser:
            return "Super admin"
        return self.role_obj.name if self.role_obj else (self.role or "No role")

    @cached_property
    def perm_codes(self) -> frozenset:
        if not self.is_active:
            return frozenset()
        if self.is_superuser:
            return frozenset(ALL_PERMISSIONS)
        return frozenset(self.role_obj.permissions if self.role_obj else [])

    def has_perm_code(self, code: str) -> bool:
        return code in self.perm_codes

    @property
    def can(self):
        return _Can(self.perm_codes)

    def can_view_org(self, org_id) -> bool:
        return self.has_perm_code("view_all_orgs") or self.organization_id == org_id

    def __str__(self):
        return self.username
