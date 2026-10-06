from django.db import migrations, models


def seed_roles(apps, schema_editor):
    from accounts.permissions import DEFAULT_ROLES

    Role = apps.get_model("accounts", "Role")
    for r in DEFAULT_ROLES:
        Role.objects.get_or_create(
            slug=r["slug"],
            defaults={
                "name": r["name"],
                "description": r["description"],
                "permissions": r["permissions"],
                "is_system": True,
                "is_default": r["is_default"],
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Role",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("slug", models.SlugField(help_text="Internal key; cannot be changed after creation.", unique=True)),
                ("name", models.CharField(max_length=100, unique=True)),
                ("description", models.CharField(blank=True, max_length=255)),
                ("permissions", models.JSONField(blank=True, default=list)),
                ("is_system", models.BooleanField(default=False, help_text="Built-in roles can be edited but not deleted.")),
                ("is_default", models.BooleanField(default=False, help_text="Given to people who sign up themselves.")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(default="uploader", help_text="Slug of the user's Role.", max_length=50),
        ),
        migrations.AlterField(
            model_name="user",
            name="organization",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name="users",
                to="ingestion.organization",
                help_text="Users without 'see all organizations' see only this organization's submissions.",
            ),
        ),
        migrations.RunPython(seed_roles, migrations.RunPython.noop),
    ]
