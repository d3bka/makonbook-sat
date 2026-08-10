"""Sitemaps for the public, crawlable surface of the site.

Almost every URL in this project sits behind ``@login_required`` or a guest
session, so a crawler reaching it only ever sees a redirect to ``/login/``.
Only pages that render real content for an anonymous visitor belong here; the
gated prefixes are turned away in ``templates/robots.txt`` instead.
"""

from django.conf import settings
from django.contrib.sitemaps import Sitemap
from django.db.models import Q
from django.urls import reverse, reverse_lazy

from apps.apclasses.models import APExamEvent


class CanonicalSitemap(Sitemap):
    """Base sitemap pinned to the canonical domain.

    ``django.contrib.sites`` is installed (allauth needs it), so the stock
    sitemap would build URLs from the ``django_site`` row. That row is the
    stock ``example.com`` on this deployment, and the app answers on four
    hostnames besides. Reading the domain from settings keeps the emitted URLs
    correct without depending on database content.
    """

    def get_domain(self, site=None):
        return settings.SITE_DOMAIN

    def get_protocol(self, protocol=None):
        return settings.SITE_PROTOCOL


class StaticViewSitemap(CanonicalSitemap):
    """Fixed pages that an anonymous visitor can load in full.

    ``/software/`` is deliberately absent: ClientSoftwareMiddleware bounces it
    to ``/sat/`` for every user agent except the desktop client, so a crawler
    never sees the page.

    The landing page is listed by path rather than by ``reverse("home")``.
    ``apps/sat/urls.py`` registers a second view under the name ``home`` and is
    included after ``apps.base.urls``, so that name resolves to ``/sat/``.
    """

    # (path, priority, changefreq)
    pages = [
        ("/", 1.0, "weekly"),
        (reverse_lazy("register"), 0.7, "monthly"),
        (reverse_lazy("apclasses:event_list"), 0.7, "weekly"),
        (reverse_lazy("rating_home"), 0.6, "daily"),
    ]

    def items(self):
        return self.pages

    def location(self, item):
        return str(item[0])

    def priority(self, item):
        return item[1]

    def changefreq(self, item):
        return item[2]


class APEventSitemap(CanonicalSitemap):
    """Published AP mock exam events that are visible without an account.

    Mirrors ``APExamEvent.user_can_see`` for an anonymous user: public, global,
    on a published exam, and not attached to a deactivated AP class.
    """

    changefreq = "weekly"
    priority = 0.6

    def items(self):
        return (
            APExamEvent.objects.filter(
                is_public=True,
                is_global=True,
                exam__status="published",
            )
            .filter(Q(exam__ap_class__isnull=True) | Q(exam__ap_class__is_active=True))
            .select_related("exam", "exam__ap_class")
            .order_by("-updated_at")
        )

    def location(self, item):
        return reverse("apclasses:event_detail", kwargs={"slug": item.slug})

    def lastmod(self, item):
        return item.updated_at


sitemaps = {
    "static": StaticViewSitemap,
    "ap-events": APEventSitemap,
}
