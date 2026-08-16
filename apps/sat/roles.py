"""Authoritative role checks for MakonBook.

Django Groups are the source of truth for staff-side roles. Related business
objects (for example a Classroom owned by a user or a SupportTeacherProfile)
never grant a role by themselves.
"""

from django.core.exceptions import ObjectDoesNotExist


TEACHER_GROUP = "Teacher"
MANAGER_GROUP = "Manager"
ADMIN_GROUP = "Admin"
SUPPORT_TEACHER_GROUP = "Support Teacher"


def _authenticated(user):
    return bool(user and getattr(user, "is_authenticated", False))


def in_group(user, name):
    if not _authenticated(user):
        return False
    return user.groups.filter(name__iexact=name).exists()


def is_platform_admin(user):
    return bool(
        _authenticated(user)
        and (
            getattr(user, "is_superuser", False)
            or getattr(user, "is_staff", False)
            or in_group(user, ADMIN_GROUP)
        )
    )


def is_manager(user):
    """Manager is an explicit group role; profiles/ownership never imply it."""
    return bool(_authenticated(user) and in_group(user, MANAGER_GROUP))


def is_teacher(user):
    """Teacher identity comes only from the Teacher Django Group.

    ``is_staff``, ``is_superuser`` and Classroom ownership are separate powers;
    none of them silently turns an account into a Teacher. Administrative
    overrides are handled explicitly at the endpoint that needs them.
    """
    return bool(_authenticated(user) and in_group(user, TEACHER_GROUP))


def support_teacher_profile(user, *, require_active=True):
    """Return the profile only when the Support Teacher group is authoritative."""
    if not _authenticated(user) or not in_group(user, SUPPORT_TEACHER_GROUP):
        return None
    try:
        profile = user.support_teacher_profile
    except (AttributeError, ObjectDoesNotExist):
        return None
    if require_active and not getattr(profile, "is_active", False):
        return None
    return profile


def is_support_teacher(user, *, require_active=True):
    return support_teacher_profile(user, require_active=require_active) is not None


def can_manage_classroom(user, classroom):
    """True for the authoritative teacher owner or a superuser.

    Merely being stored in ``Classroom.teacher`` is intentionally insufficient:
    removing the Teacher group revokes access immediately without deleting the
    classroom or its historical data.
    """
    if not _authenticated(user) or classroom is None:
        return False
    if getattr(user, "is_superuser", False):
        return True
    return bool(is_teacher(user) and classroom.teacher_id == user.id)
