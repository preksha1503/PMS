from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import Project, RoleRequest, User

PROJECT_STATUS_CHOICES = [
    ("Planning", "Planning"),
    ("Pending", "Pending"),
    ("In Progress", "In Progress"),
    ("Completed", "Completed"),
    ("On Hold", "On Hold"),
]


class SignupForm(UserCreationForm):
    full_name = forms.CharField(required=True)

    class Meta:
        model = User
        fields = ("full_name", "email", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["full_name"].label = "Full Name"
        self.fields["email"].label = "Email Address"
        self.fields["password1"].label = "Password"
        self.fields["password2"].label = "Confirm Password"

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        if User.objects.filter(username__iexact=email).exists():
            raise forms.ValidationError("This email is already used as a username.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        full_name = (self.cleaned_data.get("full_name") or "").strip()
        name_parts = full_name.split()
        user.first_name = name_parts[0] if name_parts else ""
        user.last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""
        user.email = self.cleaned_data["email"]
        user.username = self.cleaned_data["email"]
        user.role = User.Role.PENDING
        if commit:
            user.save()
        return user


class LoginForm(AuthenticationForm):
    username = forms.CharField(widget=forms.TextInput(attrs={"autofocus": True}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Username (Email)"
        self.fields["password"].label = "Password"

    class Meta:
        model = User
        fields = ("username", "password")


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = [
            "serial_number",
            "website_url",
            "stakeholder_ministry",
            "stakeholder_department",
            "stakeholder_state",
            "stakeholder_state_ministry_department",
            "stakeholder_organization",
            "initiative_scheme_project_portal",
            "genesis",
            "year",
            "project_manager_gis",
            "project_manager_sw_mobi",
            "start",
            "end",
            "status",
        ]
        widgets = {
            "start": forms.DateInput(attrs={"type": "date"}),
            "end": forms.DateInput(attrs={"type": "date"}),
            "status": forms.Select(choices=PROJECT_STATUS_CHOICES),
        }


class AssignProjectForm(forms.Form):
    search_project = forms.CharField(
        label="Search Project",
        widget=forms.TextInput(
            attrs={
                "placeholder": "Type project id, name, initiative or stakeholder...",
                "autocomplete": "off",
            }
        ),
    )
    assigned_role = forms.ChoiceField(choices=[], required=True)
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "Optional assignment notes..."}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        allowed_roles = [
            User.Role.DIRECTOR,
            User.Role.PROJECT_DIRECTOR,
            User.Role.PROJECT_MANAGER,
            User.Role.ASSISTANT_PROJECT_MANAGER,
            User.Role.DEVELOPER,
        ]
        self.fields["assigned_role"].choices = [
            (value, label) for value, label in User.Role.choices if value in allowed_roles
        ]
        self.fields["assigned_role"].label = "Assign Role"
