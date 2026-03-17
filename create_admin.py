import os

import django


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()

    from django.contrib.auth import get_user_model  # noqa: WPS433

    User = get_user_model()
    email = "admin@gmail.com"
    password = "admin@123"

    user = User.objects.filter(email=email).first()
    if user is None:
        user = User(
            username=email,
            email=email,
            role=User.Role.SUPER_ADMIN,
            is_staff=True,
            is_superuser=True,
        )
        user.set_password(password)
        user.save()
        print(f"Created superuser: {email}")
        return

    updated = False
    if user.username != email:
        user.username = email
        updated = True
    if user.email != email:
        user.email = email
        updated = True
    if user.role != User.Role.SUPER_ADMIN:
        user.role = User.Role.SUPER_ADMIN
        updated = True
    if not user.is_staff:
        user.is_staff = True
        updated = True
    if not user.is_superuser:
        user.is_superuser = True
        updated = True

    user.set_password(password)
    user.save()
    print(f"Updated superuser: {email}")


if __name__ == "__main__":
    main()
