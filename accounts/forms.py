from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.password_validation import validate_password
from django.utils.text import slugify

from .models import Role, User
from .permissions import ALL_PERMISSIONS, PERMISSION_GROUPS
from ingestion.models import Organization


class SignUpForm(UserCreationForm):
    """
    Public signup. Deliberately does NOT expose `role` — every self-signup
    gets the role marked "default" (Uploader out of the box). Changing
    someone's role is a super-admin action on the Users screen.
    """

    email = forms.EmailField(required=True)
    organization = forms.ModelChoiceField(
        queryset=Organization.objects.all().order_by("name"),
        help_text="Which organization are you uploading data for?",
    )

    class Meta:
        model = User
        fields = ("username", "email", "organization", "password1", "password2")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.organization = self.cleaned_data["organization"]
        user.role = Role.default_slug()
        if commit:
            user.save()
        return user


def _role_choices():
    return [(r.slug, r.name) for r in Role.objects.order_by("name")]


class _UserFieldsMixin(forms.ModelForm):
    role = forms.ChoiceField(choices=())
    organization = forms.ModelChoiceField(
        queryset=Organization.objects.order_by("name"), required=False,
        help_text="Users whose role can't see all organizations only see this one's submissions.",
    )

    class Meta:
        model = User
        fields = ("username", "first_name", "last_name", "email", "organization", "role", "is_active", "is_superuser")
        labels = {"is_active": "Active (can log in)", "is_superuser": "Super admin (all permissions, manages users & roles)"}

    def __init__(self, *args, acting_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.acting_user = acting_user
        self.fields["role"].choices = _role_choices()
        self.fields["email"].required = False

    def clean(self):
        data = super().clean()
        target = self.instance
        if self.acting_user and target.pk and target.pk == self.acting_user.pk:
            if not data.get("is_active"):
                self.add_error("is_active", "You can't deactivate your own account.")
            if not data.get("is_superuser"):
                self.add_error("is_superuser", "You can't remove your own super admin access.")
        return data


class UserCreateForm(_UserFieldsMixin, UserCreationForm):
    class Meta(_UserFieldsMixin.Meta):
        fields = _UserFieldsMixin.Meta.fields

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["is_active"].initial = True
        self.fields["role"].initial = Role.default_slug()


class UserEditForm(_UserFieldsMixin):
    new_password1 = forms.CharField(label="New password", required=False, widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
                                    help_text="Leave blank to keep the current password.")
    new_password2 = forms.CharField(label="Confirm new password", required=False, widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))

    def clean(self):
        data = super().clean()
        p1, p2 = data.get("new_password1"), data.get("new_password2")
        if p1 or p2:
            if p1 != p2:
                self.add_error("new_password2", "The two passwords don't match.")
            else:
                try:
                    validate_password(p1, self.instance)
                except forms.ValidationError as e:
                    self.add_error("new_password1", e)
        return data

    def save(self, commit=True):
        user = super().save(commit=False)
        if self.cleaned_data.get("new_password1"):
            user.set_password(self.cleaned_data["new_password1"])
        if commit:
            user.save()
        return user


class RoleForm(forms.ModelForm):
    permissions = forms.MultipleChoiceField(
        choices=[(c, l) for _, perms in PERMISSION_GROUPS for c, l in perms],
        required=False, widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = Role
        fields = ("name", "slug", "description", "is_default", "permissions")
        labels = {"is_default": "Default role for new sign-ups", "slug": "Key"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False
        if self.instance.pk:
            self.fields["slug"].disabled = True
            self.fields["slug"].help_text = "Fixed — users are linked to the role by this key."
        else:
            self.fields["slug"].help_text = "Optional — generated from the name."

    def clean_slug(self):
        if self.instance.pk:
            return self.instance.slug
        slug = slugify(self.cleaned_data.get("slug") or self.cleaned_data.get("name") or "")[:50]
        if not slug:
            raise forms.ValidationError("Enter a name or key.")
        if Role.objects.filter(slug=slug).exists():
            raise forms.ValidationError("A role with this key already exists.")
        return slug

    def clean_permissions(self):
        perms = self.cleaned_data.get("permissions") or []
        return [p for p in ALL_PERMISSIONS if p in perms]  # stable order

    def save(self, commit=True):
        role = super().save(commit=commit)
        if commit and role.is_default:
            Role.objects.exclude(pk=role.pk).update(is_default=False)
        return role
