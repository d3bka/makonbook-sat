from django.conf import settings


def site_meta(request):
    """Expose the canonical site root to templates.

    Social-card scrapers and ``rel=canonical`` both need absolute URLs, and the
    app answers on several hostnames. Building them from ``request.get_host()``
    would make every alias advertise itself as a separate copy of the site, so
    templates use this fixed value instead.
    """
    return {"SITE_URL": settings.SITE_URL}


def test_import_meta(request):
    empty = {
        "test_import_center_allowed": False,
        "test_import_pending_reviews": 0,
        "test_import_unread_notifications": 0,
        "test_import_notifications": [],
    }
    if not getattr(request.user, "is_authenticated", False):
        return empty
    try:
        from apps.sat.models import MakonNotification, TestImportReview
        from apps.sat.roles import is_support_teacher

        manager_allowed = (
            request.user.is_superuser
            or request.user.is_staff
            or request.user.groups.filter(name__iexact="Admin").exists()
            or request.user.groups.filter(name__iexact="Manager").exists()
        )
        reviewer = is_support_teacher(request.user)
        pending = (
            TestImportReview.objects.filter(
                reviewer=request.user,
                verdict=TestImportReview.VERDICT_PENDING,
            ).count()
            if reviewer else 0
        )
        notices_qs = MakonNotification.objects.filter(user=request.user)
        unread = notices_qs.filter(is_read=False).count()
        notices = list(notices_qs.order_by("-created_at")[:8])
        return {
            "test_import_center_allowed": bool(manager_allowed or reviewer),
            "test_import_pending_reviews": pending,
            "test_import_unread_notifications": unread,
            "test_import_notifications": notices,
        }
    except Exception:
        # Keeps login/admin pages alive during the deployment window before the migration is applied.
        return empty
