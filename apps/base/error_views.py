from urllib.parse import urlsplit

from django.shortcuts import render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme


ERROR_MESSAGES = {
    400: {
        "title": "Bad Request",
        "headline": "Request could not be processed",
        "message": "The request was malformed or incomplete. Go back and try again.",
    },
    403: {
        "title": "Access Denied",
        "headline": "You do not have access",
        "message": "This page or action is not available for your account.",
    },
    404: {
        "title": "Page Not Found",
        "headline": "Page not found",
        "message": "The page you opened does not exist or was moved.",
    },
    405: {
        "title": "Action Not Allowed",
        "headline": "This action requires a button submit",
        "message": "This page cannot be opened directly. Please return to the previous page and use the correct button.",
    },
    500: {
        "title": "Server Error",
        "headline": "Something went wrong",
        "message": "The server could not complete the request. Please try again later or contact support.",
    },
}


LEGACY_DASHBOARD_PATHS = {
    "/dashboard",
    "/dashboard/",
    "/sat/dashboard",
    "/sat/dashboard/",
}


def build_error_navigation(request):
    """Return safe, role-neutral navigation links for custom error pages.

    The old template used ``javascript:history.back()``. That made the button
    unpredictable after redirects and often sent users back to the legacy
    ``/dashboard`` route. We now use a validated same-site referrer and fall
    back to the canonical classroom entry page.
    """
    if request.user.is_authenticated:
        primary_url = reverse("sat_menu")
        primary_label = "Open classrooms"
    else:
        primary_url = "/"
        primary_label = "Go home"

    back_url = ""
    referer = (request.META.get("HTTP_REFERER") or "").strip()
    if referer and url_has_allowed_host_and_scheme(
        referer,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        parsed = urlsplit(referer)
        candidate = parsed.path or "/"
        if parsed.query:
            candidate = f"{candidate}?{parsed.query}"

        current_path = request.get_full_path()
        if (
            candidate != current_path
            and parsed.path not in LEGACY_DASHBOARD_PATHS
        ):
            back_url = candidate

    return {
        "error_primary_url": primary_url,
        "error_primary_label": primary_label,
        "error_back_url": back_url or primary_url,
    }


def makon_error_page(request, exception=None, status_code=404, **kwargs):
    details = ERROR_MESSAGES.get(status_code, ERROR_MESSAGES[404]).copy()
    navigation = build_error_navigation(request)
    return render(
        request,
        "errors/makon_error.html",
        {
            "status_code": status_code,
            "error_title": details["title"],
            "error_headline": details["headline"],
            "error_message": details["message"],
            "exception": exception,
            **navigation,
        },
        status=status_code,
    )


def bad_request(request, exception=None):
    return makon_error_page(request, exception=exception, status_code=400)


def permission_denied(request, exception=None):
    return makon_error_page(request, exception=exception, status_code=403)


def page_not_found(request, exception=None):
    return makon_error_page(request, exception=exception, status_code=404)


def server_error(request):
    return makon_error_page(request, status_code=500)
