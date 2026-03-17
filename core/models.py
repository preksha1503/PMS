from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class User(AbstractUser):
    class Role(models.TextChoices):
        SUPER_ADMIN = "super_admin", "Super Admin"
        DIRECTOR = "director", "Director"
        PROJECT_DIRECTOR = "project_director", "Project Director"
        PROJECT_MANAGER = "project_manager", "Project Manager"
        ASSISTANT_PROJECT_MANAGER = "assistant_project_manager", "Assistant Project Manager"
        DEVELOPER = "developer", "Developer"
        PENDING = "pending", "Pending Approval"

    role = models.CharField(max_length=40, choices=Role.choices)

    def has_management_role(self):
        return self.role in {
            self.Role.SUPER_ADMIN,
            self.Role.DIRECTOR,
            self.Role.PROJECT_DIRECTOR,
            self.Role.PROJECT_MANAGER,
        }

    def can_manage_projects(self):
        if self.is_superuser or self.is_staff:
            return True
        return self.has_management_role()

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"


class RoleRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="role_requests")
    requested_role = models.CharField(max_length=40, choices=User.Role.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_role_requests",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.username} -> {self.requested_role} ({self.status})"


class Project(models.Model):
    serial_number = models.PositiveIntegerField("S.No.", unique=True)
    website_url = models.URLField("Website URL", max_length=300)
    stakeholder_ministry = models.CharField("Stakeholder - Ministry", max_length=200, blank=True)
    stakeholder_department = models.CharField("Stakeholder - Department", max_length=200, blank=True)
    stakeholder_state = models.CharField("Stakeholder - State", max_length=120, blank=True)
    stakeholder_state_ministry_department = models.CharField(
        "Stakeholder - State Ministry/Department",
        max_length=240,
        blank=True,
    )
    stakeholder_organization = models.CharField("Stakeholder - Organization", max_length=240, blank=True)
    initiative_scheme_project_portal = models.CharField(
        "Initiative/Scheme/Project Portal",
        max_length=300,
    )
    genesis = models.TextField("Genesis", blank=True)
    year = models.PositiveIntegerField("Year")
    project_manager_gis = models.CharField("Project Manager - GIS", max_length=150, blank=True)
    project_manager_sw_mobi = models.CharField("Project Manager - S/W & Mobi", max_length=150, blank=True)
    start = models.DateField("Start")
    end = models.DateField("End")
    status = models.CharField("Status", max_length=120)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_projects",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["serial_number"]

    def clean(self):
        if self.end < self.start:
            raise ValidationError({"end": "End date must be after start date."})

    def __str__(self):
        return f"{self.serial_number} - {self.initiative_scheme_project_portal}"


class ProjectAssignment(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="assignments")
    assigned_to = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="project_assignments",
        null=True,
        blank=True,
    )
    assigned_role = models.CharField(max_length=40, choices=User.Role.choices, blank=True)
    assigned_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="given_assignments")
    notes = models.TextField(blank=True)
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-assigned_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "assigned_to"],
                name="unique_project_assignment_per_user",
                condition=Q(assigned_to__isnull=False),
            ),
            models.UniqueConstraint(
                fields=["project", "assigned_role"],
                name="unique_project_assignment_per_role",
                condition=Q(assigned_role__gt=""),
            )
        ]

    def __str__(self):
        if self.assigned_to:
            return f"{self.project} -> {self.assigned_to.username}"
        if self.assigned_role:
            return f"{self.project} -> {self.get_assigned_role_display()}"
        return f"{self.project} -> Unassigned"
