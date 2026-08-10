from django.conf import settings


def site_meta(request):
    """Expose the canonical site root to templates.

    Social-card scrapers and ``rel=canonical`` both need absolute URLs, and the
    app answers on several hostnames. Building them from ``request.get_host()``
    would make every alias advertise itself as a separate copy of the site, so
    templates use this fixed value instead.
    """
    return {"SITE_URL": settings.SITE_URL}
