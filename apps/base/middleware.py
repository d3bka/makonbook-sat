from django.shortcuts import render


class MakonErrorPageMiddleware:
    """Render MakonBook-style error pages for normal HTML requests.

    JSON/AJAX/API responses are intentionally left untouched.
    Chrome DevTools sometimes requests /.well-known/appspecific/com.chrome.devtools.json;
    that request should not be converted into a custom TemplateResponse.
    """

    HTML_ERROR_STATUSES = {400, 403, 404, 405}

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        return self._maybe_replace_response(request, response)

    def process_exception(self, request, exception):
        # Do not hide debug tracebacks during development. Production uses handler500.
        return None

    def _wants_html(self, request):
        accept = request.headers.get("Accept", "")
        requested_with = request.headers.get("X-Requested-With", "")
        path = request.path or ""

        if requested_with.lower() == "xmlhttprequest":
            return False
        if path.startswith("/.well-known/"):
            return False
        if path.startswith("/static/") or path.startswith("/media/"):
            return False
        if path.startswith("/sat/check_the_answers"):
            return False
        if path.startswith("/accounts/") or path.startswith("/admin/"):
            return False
        if "application/json" in accept and "text/html" not in accept:
            return False
        return True

    def _maybe_replace_response(self, request, response):
        if response.status_code not in self.HTML_ERROR_STATUSES:
            return response
        if not self._wants_html(request):
            return response
        if getattr(response, "streaming", False):
            return response

        from apps.base.error_views import ERROR_MESSAGES, build_error_navigation

        details = ERROR_MESSAGES.get(response.status_code, ERROR_MESSAGES[404])
        navigation = build_error_navigation(request)
        # Important: return a fully rendered HttpResponse, not TemplateResponse.
        # Otherwise django.middleware.common.CommonMiddleware can access
        # response.content before render() and raise ContentNotRenderedError.
        return render(
            request,
            "errors/makon_error.html",
            {
                "status_code": response.status_code,
                "error_title": details["title"],
                "error_headline": details["headline"],
                "error_message": details["message"],
                **navigation,
            },
            status=response.status_code,
        )
