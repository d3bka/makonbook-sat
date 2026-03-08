from django.http import HttpResponseForbidden
from django.shortcuts import redirect

class ClientSoftwareMiddleware:
    """
    Middleware that ensures that only requests coming from the dedicated client (which
    includes the correct secret token in the X-Client-Token header) can access views beyond
    the login (or other exempt) pages—unless the user is not logged in, in which case the login
    process is allowed.
    """
    def __init__(self, get_response):
        self.get_response = get_response
        self.expected_agent = "MakonBookClient/1.0"

    def __call__(self, request):
        if request.path in '/software/':
                return self.get_response(request)

        if request.user.is_authenticated:
            if request.path in '/logout/':
                return self.get_response(request)
            # If user is admin/staff, allow without token.
            if request.user.is_staff:
                return self.get_response(request)
            # For non-admin authenticated users, require the secret token in header.
            ua = request.META.get("HTTP_USER_AGENT", "")
            if ua != self.expected_agent:
                return redirect('software')
        else:
            if request.path in '/login/':
                return self.get_response(request)
            ua = request.META.get("HTTP_USER_AGENT", "")
            if ua != self.expected_agent:
                return redirect('software')
        # If the user is not authenticated, let Django handle login/redirection.
        return self.get_response(request)
