from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Project, ProjectAssignment, User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("Role Access", {"fields": ("role",)}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Role Access", {"fields": ("role",)}),
    )
    list_display = ("username", "email", "role", "is_staff", "is_superuser")
    list_filter = ("role", "is_staff", "is_superuser", "is_active")


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = (
        "serial_number",
        "initiative_scheme_project_portal",
        "year",
        "status",
        "project_manager_gis",
        "project_manager_sw_mobi",
    )
    search_fields = (
        "initiative_scheme_project_portal",
        "project_manager_gis",
        "project_manager_sw_mobi",
        "status",
    )


@admin.register(ProjectAssignment)
class ProjectAssignmentAdmin(admin.ModelAdmin):
    list_display = ("project", "assigned_to", "assigned_by", "assigned_at")
    search_fields = ("project__initiative_scheme_project_portal", "assigned_to__username", "assigned_by__username")

