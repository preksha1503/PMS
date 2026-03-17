from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.views import PasswordChangeView
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone

from .forms import AssignProjectForm, LoginForm, ProjectForm, SignupForm
from .models import Project, ProjectAssignment, RoleRequest, User


def uses_director_ui(user):
    return user.is_superuser or user.has_management_role()


def normalize_status(value):
    normalized = (value or "").strip().lower()
    if "plan" in normalized:
        return "planning"
    if "complete" in normalized:
        return "completed"
    if "hold" in normalized:
        return "on_hold"
    if "progress" in normalized:
        return "in_progress"
    if "pending" in normalized:
        return "pending"
    return "pending"


def get_status_counts(projects):
    status_groups = projects.values("status").annotate(count=Count("id"))
    counts = {
        "planning": 0,
        "pending": 0,
        "completed": 0,
        "on_hold": 0,
        "in_progress": 0,
    }
    for item in status_groups:
        counts[normalize_status(item["status"])] += item["count"]
    return counts


def resolve_project_from_search(search_value):
    value = (search_value or "").strip()
    if not value:
        return None

    serial_part = value.split("-", 1)[0].strip()
    if serial_part.isdigit():
        project = Project.objects.filter(serial_number=int(serial_part)).first()
        if project:
            return project

    exact = Project.objects.filter(
        Q(initiative_scheme_project_portal__iexact=value)
        | Q(stakeholder_ministry__iexact=value)
        | Q(stakeholder_department__iexact=value)
        | Q(stakeholder_organization__iexact=value)
    ).first()
    if exact:
        return exact

    matches = Project.objects.filter(
        Q(initiative_scheme_project_portal__icontains=value)
        | Q(stakeholder_ministry__icontains=value)
        | Q(stakeholder_department__icontains=value)
        | Q(stakeholder_state__icontains=value)
        | Q(stakeholder_organization__icontains=value)
    ).order_by("serial_number")
    if matches.count() == 1:
        return matches.first()
    return None


def to_int_or_default(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def import_projects_from_excel(uploaded_file, created_by):
    try:
        from openpyxl import load_workbook
    except ModuleNotFoundError as exc:
        raise RuntimeError("openpyxl is not installed.") from exc

    wb = load_workbook(uploaded_file, data_only=True)
    ws = wb.active
    imported = 0
    updated = 0

    for row in ws.iter_rows(min_row=3, values_only=True):
        if not row or all(cell is None or str(cell).strip() == "" for cell in row):
            continue

        serial_number = to_int_or_default(row[0], 0)
        website_url = (row[1] or "").strip() if row[1] else ""
        if not serial_number or not website_url:
            continue

        defaults = {
            "website_url": website_url,
            "stakeholder_ministry": (row[2] or "").strip() if row[2] else "",
            "stakeholder_department": (row[3] or "").strip() if row[3] else "",
            "stakeholder_state": (row[4] or "").strip() if row[4] else "",
            "stakeholder_state_ministry_department": (row[5] or "").strip() if row[5] else "",
            "stakeholder_organization": (row[6] or "").strip() if row[6] else "",
            "initiative_scheme_project_portal": (row[7] or "").strip() if row[7] else "",
            "genesis": (row[8] or "").strip() if row[8] else "",
            "year": to_int_or_default(row[9], timezone.now().year),
            "project_manager_gis": (row[10] or "").strip() if row[10] else "",
            "project_manager_sw_mobi": (row[11] or "").strip() if row[11] else "",
            "start": row[12] if row[12] else timezone.now().date(),
            "end": row[13] if row[13] else timezone.now().date(),
            "status": (row[14] or "Pending").strip() if row[14] else "Pending",
            "created_by": created_by,
        }
        _, was_created = Project.objects.update_or_create(
            serial_number=serial_number,
            defaults=defaults,
        )
        if was_created:
            imported += 1
        else:
            updated += 1

    return imported, updated


def signup_view(request):
    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("role_request")
    else:
        form = SignupForm()
    return render(request, "core/signup.html", {"form": form})


def login_view(request):
    form = LoginForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        login(request, form.get_user())
        return redirect("dashboard")
    return render(request, "core/login.html", {"form": form})


def logout_view(request):
    logout(request)
    return redirect("login")


@login_required
def dashboard_view(request):
    if request.user.is_superuser or request.user.role == User.Role.SUPER_ADMIN:
        return redirect("super_admin_dashboard")
    if request.user.role == User.Role.PENDING:
        return redirect("role_request")
    if not request.user.has_management_role() and not request.user.is_superuser:
        return redirect("view_projects")
    projects = Project.objects.all()
    status_counts = get_status_counts(projects)
    total_projects = projects.count()
    total_users = User.objects.count()
    month_label = timezone.now().strftime("%b %Y")

    def percent(count):
        if total_projects == 0:
            return 0
        return round((count / total_projects) * 100, 2)

    segments = [
        ("pending", "#3f7ae0", percent(status_counts["pending"])),
        ("in_progress", "#f2c01f", percent(status_counts["in_progress"])),
        ("completed", "#5fcb85", percent(status_counts["completed"])),
        ("on_hold", "#ec6e6e", percent(status_counts["on_hold"])),
        ("planning", "#94a0b5", percent(status_counts["planning"])),
    ]
    if total_projects == 0:
        pie_style = ""
    else:
        cursor = 0.0
        parts = []
        for _, color, pct in segments:
            end = cursor + pct
            parts.append(f"{color} {cursor:.2f}% {end:.2f}%")
            cursor = end
        pie_style = f"background: conic-gradient({', '.join(parts)});"

    max_count = max(status_counts.values()) if total_projects else 0
    if max_count == 0:
        bar_heights = {key: 0 for key in status_counts}
    else:
        bar_heights = {
            key: round((value / max_count) * 100, 1)
            for key, value in status_counts.items()
        }

    return render(
        request,
        "core/director_dashboard.html",
        {
            "status_counts": status_counts,
            "total_projects": total_projects,
            "total_users": total_users,
            "pie_style": pie_style,
            "pie_empty": total_projects == 0,
            "bar_heights": bar_heights,
            "month_label": month_label,
        },
    )


@login_required
def super_admin_dashboard_view(request):
    if not request.user.is_superuser and request.user.role != User.Role.SUPER_ADMIN:
        return redirect("dashboard")

    projects = Project.objects.all()
    status_counts = get_status_counts(projects)
    total_projects = projects.count()
    total_users = User.objects.count()
    total_pending_requests = RoleRequest.objects.filter(status=RoleRequest.Status.PENDING).count()
    month_label = timezone.now().strftime("%b %Y")

    def percent(count):
        if total_projects == 0:
            return 0
        return round((count / total_projects) * 100, 2)

    segments = [
        ("pending", "#3f7ae0", percent(status_counts["pending"])),
        ("in_progress", "#f2c01f", percent(status_counts["in_progress"])),
        ("completed", "#5fcb85", percent(status_counts["completed"])),
        ("on_hold", "#ec6e6e", percent(status_counts["on_hold"])),
        ("planning", "#94a0b5", percent(status_counts["planning"])),
    ]
    if total_projects == 0:
        pie_style = ""
    else:
        cursor = 0.0
        parts = []
        for _, color, pct in segments:
            end = cursor + pct
            parts.append(f"{color} {cursor:.2f}% {end:.2f}%")
            cursor = end
        pie_style = f"background: conic-gradient({', '.join(parts)});"

    max_count = max(status_counts.values()) if total_projects else 0
    if max_count == 0:
        bar_heights = {key: 0 for key in status_counts}
    else:
        bar_heights = {
            key: round((value / max_count) * 100, 1)
            for key, value in status_counts.items()
        }

    temp_credentials = None
    if request.method == "POST" and request.POST.get("action") == "generate_temp_admin":
        base = timezone.now().strftime("%Y%m%d%H%M%S")
        username = f"temp_super_admin_{base}"
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"temp_super_admin_{base}_{counter}"
            counter += 1
        password = User.objects.make_random_password(length=12)
        temp_user = User.objects.create_user(username=username, password=password, role=User.Role.SUPER_ADMIN)
        temp_user.is_staff = True
        temp_user.is_superuser = True
        temp_user.save(update_fields=["is_staff", "is_superuser"])
        temp_credentials = {"username": username, "password": password}
        messages.success(request, "Temporary super admin created. Copy the credentials now.")

    page_links = [
        {"label": "Dashboard", "url": "dashboard"},
        {"label": "User Management", "url": "super_admin_users"},
        {"label": "Add Project", "url": "project_create"},
        {"label": "View Projects", "url": "view_projects"},
        {"label": "Assign Project", "url": "assign_project"},
        {"label": "Assign To", "url": "assign_to"},
        {"label": "Excel Entry", "url": "excel_entry"},
        {"label": "Role Access", "url": "role_access"},
        {"label": "Profile", "url": "profile"},
        {"label": "Change Password", "url": "change_password"},
        {"label": "Help", "url": "help_page"},
        {"label": "Contact Us", "url": "contact_us"},
        {"label": "Chat", "url": "chat_page"},
        {"label": "Notifications", "url": "notifications_page"},
    ]

    return render(
        request,
        "core/super_admin_dashboard.html",
        {
            "status_counts": status_counts,
            "total_projects": total_projects,
            "total_users": total_users,
            "pie_style": pie_style,
            "pie_empty": total_projects == 0,
            "bar_heights": bar_heights,
            "month_label": month_label,
            "total_pending_requests": total_pending_requests,
            "temp_credentials": temp_credentials,
            "page_links": page_links,
        },
    )


@login_required
def super_admin_users_view(request):
    if not request.user.is_superuser and request.user.role != User.Role.SUPER_ADMIN:
        return redirect("dashboard")

    q = (request.GET.get("q") or "").strip()
    role_filter = (request.GET.get("role") or "").strip()
    users = User.objects.all().order_by("username")
    if q:
        users = users.filter(
            Q(username__icontains=q)
            | Q(email__icontains=q)
            | Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
        )
    if role_filter:
        users = users.filter(role=role_filter)

    if request.method == "POST":
        action = request.POST.get("action")
        target_id = request.POST.get("user_id")
        target = User.objects.filter(id=target_id).first()
        if not target:
            messages.error(request, "User not found.")
            return redirect("super_admin_users")

        if action == "set_role":
            role_value = (request.POST.get("role") or "").strip()
            allowed_values = {value for value, _ in User.Role.choices}
            confirm_super_admin = request.POST.get("confirm_super_admin") == "yes"
            if role_value not in allowed_values:
                messages.error(request, "Please select a valid role.")
            elif role_value == User.Role.SUPER_ADMIN and not confirm_super_admin:
                messages.error(request, "Confirm Super Admin assignment before updating the role.")
            else:
                target.role = role_value
                target.save(update_fields=["role"])
                messages.success(request, f"Updated role for {target.username}.")
        elif action == "toggle_active":
            if target.id == request.user.id:
                messages.error(request, "You cannot deactivate your own account.")
            else:
                target.is_active = not target.is_active
                target.save(update_fields=["is_active"])
                state = "activated" if target.is_active else "deactivated"
                messages.success(request, f"{target.username} has been {state}.")
        else:
            messages.error(request, "Invalid action.")

        return redirect("super_admin_users")

    return render(
        request,
        "core/super_admin_users.html",
        {
            "users": users,
            "q": q,
            "role_filter": role_filter,
            "role_choices": User.Role.choices,
        },
    )


@login_required
def project_create_view(request):
    if not request.user.can_manage_projects():
        return redirect("dashboard")
    if request.method == "POST":
        form = ProjectForm(request.POST)
        if form.is_valid():
            project = form.save(commit=False)
            project.created_by = request.user
            project.save()
            return redirect("dashboard")
    else:
        form = ProjectForm()
    template_name = "core/director_project_form.html" if uses_director_ui(request.user) else "core/project_form.html"
    return render(request, template_name, {"form": form, "mode": "Create"})


@login_required
def project_edit_view(request, project_id):
    if not request.user.can_manage_projects():
        return redirect("dashboard")
    project = get_object_or_404(Project, id=project_id)
    if request.method == "POST":
        form = ProjectForm(request.POST, instance=project)
        if form.is_valid():
            form.save()
            return redirect("dashboard")
    else:
        form = ProjectForm(instance=project)
    template_name = "core/director_project_form.html" if uses_director_ui(request.user) else "core/project_form.html"
    return render(request, template_name, {"form": form, "mode": "Edit"})


@login_required
def project_delete_view(request, project_id):
    if not request.user.can_manage_projects():
        return redirect("dashboard")
    project = get_object_or_404(Project, id=project_id)
    if request.method == "POST":
        project.delete()
        messages.success(request, "Project deleted successfully.")
    return redirect("view_projects")


@login_required
def assign_project_view(request):
    return _assign_page_handler(request, active_page="assign_project", page_title="Assign Project")


@login_required
def assign_to_view(request):
    q = (request.GET.get("q") or "").strip()
    assignments = ProjectAssignment.objects.select_related("project", "assigned_to", "assigned_by")
    if not request.user.can_manage_projects():
        assignments = assignments.filter(assigned_to=request.user)
    if q:
        assignments = assignments.filter(
            Q(project__initiative_scheme_project_portal__icontains=q)
            | Q(project__stakeholder_organization__icontains=q)
            | Q(project__status__icontains=q)
            | Q(assigned_to__username__icontains=q)
            | Q(assigned_by__username__icontains=q)
            | Q(assigned_role__icontains=q)
        )
        if q.isdigit():
            assignments = assignments | ProjectAssignment.objects.select_related(
                "project", "assigned_to", "assigned_by"
            ).filter(project__serial_number=int(q))
    assignments = assignments.order_by("-assigned_at").distinct()
    return render(
        request,
        "core/director_assign_to.html",
        {
            "assignments": assignments,
            "q": q,
            "total_assignments": assignments.count(),
        },
    )


def _assign_page_handler(request, active_page, page_title):
    if not request.user.can_manage_projects():
        return redirect("dashboard")

    if request.method == "POST":
        form = AssignProjectForm(request.POST)
        if form.is_valid():
            project = resolve_project_from_search(form.cleaned_data["search_project"])
            if not project:
                form.add_error("search_project", "Project not found. Use exact serial number or select from suggestions.")
            else:
                ProjectAssignment.objects.update_or_create(
                    project=project,
                    assigned_role=form.cleaned_data["assigned_role"],
                    defaults={
                        "assigned_by": request.user,
                        "notes": form.cleaned_data["notes"],
                        "assigned_to": None,
                    },
                )
                messages.success(request, "Project assigned successfully.")
                return redirect(active_page)
    else:
        form = AssignProjectForm()

    project_suggestions = Project.objects.order_by("serial_number").values(
        "serial_number",
        "initiative_scheme_project_portal",
        "stakeholder_organization",
    )
    return render(
        request,
        "core/director_assign_project.html",
        {
            "form": form,
            "project_suggestions": project_suggestions,
            "active_page": active_page,
            "page_title": page_title,
        },
    )


@login_required
def view_projects_view(request):
    if request.user.role == User.Role.PENDING:
        return redirect("role_request")
    projects = Project.objects.all()
    q = (request.GET.get("q") or "").strip()
    status_filter = (request.GET.get("status") or "").strip()

    filtered_projects = projects
    if q:
        query_filter = (
            Q(initiative_scheme_project_portal__icontains=q)
            | Q(stakeholder_ministry__icontains=q)
            | Q(stakeholder_department__icontains=q)
            | Q(stakeholder_state__icontains=q)
            | Q(stakeholder_organization__icontains=q)
            | Q(project_manager_gis__icontains=q)
            | Q(project_manager_sw_mobi__icontains=q)
        )
        if q.isdigit():
            query_filter = query_filter | Q(serial_number=int(q))
        filtered_projects = filtered_projects.filter(query_filter)
    if status_filter:
        filtered_projects = [p for p in filtered_projects if normalize_status(p.status) == status_filter]
    else:
        filtered_projects = list(filtered_projects)

    status_counts = get_status_counts(projects)
    return render(
        request,
        "core/director_view_projects.html",
        {
            "projects": filtered_projects,
            "total_projects": projects.count(),
            "showing_count": len(filtered_projects),
            "status_counts": status_counts,
            "q": q,
            "status_filter": status_filter,
            "can_manage": request.user.can_manage_projects(),
        },
    )


@login_required
def excel_entry_view(request):
    if not request.user.can_manage_projects():
        return redirect("dashboard")

    if request.method == "POST":
        upload = request.FILES.get("excel_file")
        if not upload:
            messages.error(request, "Please choose an Excel file.")
        elif not upload.name.lower().endswith(".xlsx"):
            messages.error(request, "Only .xlsx files are supported. Please save your file as .xlsx.")
        else:
            try:
                imported, updated = import_projects_from_excel(upload, request.user)
                messages.success(request, f"Import complete. Added {imported} and updated {updated} projects.")
                return redirect("excel_entry")
            except RuntimeError as exc:
                messages.error(request, f"{exc} Install it with: pip install openpyxl")
            except Exception:
                messages.error(request, "Could not import this file. Please verify the sheet format.")

    return render(request, "core/director_excel_entry.html")


@login_required
def profile_view(request):
    user = request.user
    context = {
        "profile_name": user.get_full_name() or user.username,
        "profile_role": user.get_role_display() if hasattr(user, "get_role_display") else "N/A",
        "email": user.email or "N/A",
        "department": "N/A",
        "employee_id": "N/A",
        "phone": "N/A",
    }
    return render(request, "core/director_profile.html", context)


@login_required
def role_request_view(request):
    if request.user.role == User.Role.SUPER_ADMIN or request.user.is_superuser:
        return redirect("super_admin_dashboard")

    allowed_roles = [
        choice for choice in User.Role.choices if choice[0] not in (User.Role.SUPER_ADMIN, User.Role.PENDING)
    ]
    pending_request = RoleRequest.objects.filter(user=request.user, status=RoleRequest.Status.PENDING).first()
    latest_request = RoleRequest.objects.filter(user=request.user).order_by("-created_at").first()

    if request.method == "POST":
        requested_role = (request.POST.get("requested_role") or "").strip()
        allowed_values = {value for value, _ in allowed_roles}
        if requested_role not in allowed_values:
            messages.error(request, "Please select a valid role.")
        else:
            if pending_request:
                pending_request.requested_role = requested_role
                pending_request.save(update_fields=["requested_role", "updated_at"])
            else:
                RoleRequest.objects.create(user=request.user, requested_role=requested_role)
            messages.success(request, "Role request submitted for approval.")
            return redirect("role_request")

    return render(
        request,
        "core/director_role_request.html",
        {
            "allowed_roles": allowed_roles,
            "pending_request": pending_request,
            "latest_request": latest_request,
        },
    )


@login_required
def role_access_view(request):
    if request.user.role != User.Role.SUPER_ADMIN and not request.user.is_superuser:
        return redirect("dashboard")

    pending_requests = RoleRequest.objects.filter(status=RoleRequest.Status.PENDING).select_related("user")
    allowed_roles = [
        choice for choice in User.Role.choices if choice[0] not in (User.Role.SUPER_ADMIN, User.Role.PENDING)
    ]

    if request.method == "POST":
        request_id = request.POST.get("request_id")
        action = request.POST.get("action")
        role_value = request.POST.get("role")
        role_request = RoleRequest.objects.filter(id=request_id).select_related("user").first()
        if not role_request or role_request.status != RoleRequest.Status.PENDING:
            messages.error(request, "Role request not found or already processed.")
            return redirect("role_access")

        if action == "approve":
            allowed_values = {value for value, _ in allowed_roles}
            if role_value not in allowed_values:
                messages.error(request, "Please select a valid role.")
                return redirect("role_access")
            role_request.user.role = role_value
            role_request.user.save(update_fields=["role"])
            role_request.status = RoleRequest.Status.APPROVED
            role_request.reviewed_by = request.user
            role_request.reviewed_at = timezone.now()
            role_request.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])
            messages.success(request, f"Approved role for {role_request.user.username}.")
        elif action == "reject":
            role_request.status = RoleRequest.Status.REJECTED
            role_request.reviewed_by = request.user
            role_request.reviewed_at = timezone.now()
            role_request.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])
            messages.success(request, f"Rejected role request for {role_request.user.username}.")
        else:
            messages.error(request, "Invalid action.")
        return redirect("role_access")

    return render(
        request,
        "core/director_role_access.html",
        {
            "pending_requests": pending_requests,
            "allowed_roles": allowed_roles,
        },
    )


class DirectorPasswordChangeView(PasswordChangeView):
    template_name = "core/director_change_password.html"
    success_url = reverse_lazy("profile")

    def form_valid(self, form):
        messages.success(self.request, "Password updated successfully.")
        return super().form_valid(form)


@login_required
def help_view(request):
    return render(request, "core/director_help.html")


@login_required
def contact_us_view(request):
    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        email = (request.POST.get("email") or "").strip()
        message = (request.POST.get("message") or "").strip()
        if not name or not email or not message:
            messages.error(request, "Please fill all fields before submitting.")
        else:
            messages.success(request, "Your message has been submitted successfully.")
            return redirect("contact_us")
    return render(request, "core/director_contact_us.html")


@login_required
def chat_view(request):
    return render(request, "core/director_chat.html")


@login_required
def notifications_view(request):
    return render(request, "core/director_notifications.html")


