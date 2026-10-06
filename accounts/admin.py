from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Role, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (
        ("BEPRC access", {"fields": ("organization", "role")}),
    )
    list_display = ("username", "email", "organization", "role", "is_superuser", "is_active")
    list_filter = ("role", "organization", "is_superuser", "is_active")


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_default", "is_system")
    readonly_fields = ("created_at", "updated_at")
