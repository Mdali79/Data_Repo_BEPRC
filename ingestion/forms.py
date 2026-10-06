from django import forms

from .models import Organization


class UploadForm(forms.Form):
    file = forms.FileField(help_text="A Daily Report .xlsx file (filename must contain DD-MM-YYYY).")
    organization = forms.ModelChoiceField(queryset=Organization.objects.all(), required=False)

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None and not user.has_perm_code("upload_any_org"):
            # Non-admins upload only for their own organization — remove
            # the choice entirely rather than trust a hidden field.
            self.fields.pop("organization")
            self._locked_org = user.organization
        else:
            self._locked_org = None

    def clean_file(self):
        f = self.cleaned_data["file"]
        if not f.name.lower().endswith(".xlsx"):
            raise forms.ValidationError("Only .xlsx files are supported right now.")
        return f

    def get_organization(self):
        return self._locked_org or self.cleaned_data.get("organization")
