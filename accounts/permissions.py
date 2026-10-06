"""
The fixed catalog of permissions a Role can grant.

Permissions are defined in code (not in the database) because each one is
checked by a specific view — adding a permission means adding the check
too. Which ROLE gets which permission is data, edited by a superuser on
the "Roles & permissions" screen (/accounts/manage/roles/).

Superusers implicitly have every permission, and are the only accounts
that can manage users and roles.
"""

PERMISSION_GROUPS = [
    ("Dashboard & reports", [
        ("view_dashboard", "View dashboard"),
        ("view_reports", "View system hourly & plant generation reports"),
        ("export_data", "Download CSV / Excel exports"),
    ]),
    ("Submissions", [
        ("upload_reports", "Upload daily reports"),
        ("view_submissions", "View submissions"),
        ("review_submissions", "Approve / change submission status"),
        ("delete_submissions", "Delete submissions"),
    ]),
    ("Data scope", [
        ("view_all_orgs", "See submissions of all organizations (otherwise own organization only)"),
        ("upload_any_org", "Upload on behalf of any organization"),
    ]),
]

PERMISSION_LABELS = {code: label for _, perms in PERMISSION_GROUPS for code, label in perms}
ALL_PERMISSIONS = list(PERMISSION_LABELS)

# Seeded by migration 0002 — editable afterwards by a superuser.
DEFAULT_ROLES = [
    {
        "slug": "uploader", "name": "Uploader", "is_default": True,
        "description": "Uploads and tracks reports for their own organization.",
        "permissions": ["view_dashboard", "view_reports", "export_data", "upload_reports", "view_submissions"],
    },
    {
        "slug": "analyst", "name": "Analyst", "is_default": False,
        "description": "Read-only access to reports and submissions across all organizations.",
        "permissions": ["view_dashboard", "view_reports", "export_data", "view_submissions", "view_all_orgs"],
    },
    {
        "slug": "admin", "name": "Admin", "is_default": False,
        "description": "Full data access: upload for any organization, review and delete submissions.",
        "permissions": list(ALL_PERMISSIONS),
    },
]
