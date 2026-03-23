from django import forms
from django.conf import settings
from django.contrib.auth import authenticate
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
        self.fields["username"].label = "Username or Email"
        self.fields["password"].label = "Password"

    class Meta:
        model = User
        fields = ("username", "password")

    def clean(self):
        username = (self.cleaned_data.get("username") or "").strip()
        if "@" in username:
            username = username.lower()
            self.cleaned_data["username"] = username
        password = self.cleaned_data.get("password") or ""

        if username and password:
            lookup_user = None
            resolved_username = username

            if "@" in username:
                lookup_user = User.objects.filter(email__iexact=username).only("username", "is_active").first()
                if lookup_user and lookup_user.username:
                    resolved_username = lookup_user.username
            else:
                lookup_user = User.objects.filter(username__iexact=username).only("username", "is_active").first()
                if lookup_user and lookup_user.username:
                    resolved_username = lookup_user.username

            user = authenticate(self.request, username=resolved_username, password=password)

            if user is None:
                if settings.DEBUG:
                    db = settings.DATABASES.get("default", {})
                    db_hint = f" (DB: {db.get('ENGINE', 'unknown')})"
                    if lookup_user and lookup_user.is_active is False:
                        raise forms.ValidationError(f"This account is disabled.{db_hint}", code="inactive")
                    if lookup_user:
                        raise forms.ValidationError(f"Incorrect password.{db_hint}", code="invalid_password")
                    raise forms.ValidationError(
                        f"No account found with that username/email.{db_hint}",
                        code="unknown_user",
                    )
                raise self.get_invalid_login_error()

            self.confirm_login_allowed(user)
            self.user_cache = user

        return self.cleaned_data


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
    assigned_to = forms.EmailField(
        label="User Email",
        widget=forms.EmailInput(
            attrs={
                "placeholder": "Enter user email (e.g. user@example.com)",
                "autocomplete": "off",
            }
        ),
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "Optional assignment notes..."}),
    )
