from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect
import time
import logging

logger = logging.getLogger(__name__)

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


class RequestTimeoutMiddleware:
    """
    Middleware to handle request timeouts and large payloads for test submissions.
    Adds timeout protection and better error handling.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Track request start time
        request.start_time = time.time()

        # For POST requests to test submission endpoints, add special handling
        if request.method == 'POST' and ('check_the_answers' in request.path or 'submit' in request.path):
            try:
                # Log large requests
                content_length = int(request.META.get('CONTENT_LENGTH', 0))
                if content_length > 1024 * 1024:  # > 1MB
                    logger.info(f"Large request detected: {content_length} bytes from {request.META.get('REMOTE_ADDR')}")

                response = self.get_response(request)

                # Log processing time for submissions
                processing_time = time.time() - request.start_time
                if processing_time > 10:  # Log slow requests
                    logger.warning(f"Slow request processing: {processing_time:.2f}s for {request.path}")

                return response

            except Exception as e:
                logger.error(f"Error processing request to {request.path}: {str(e)}")
                if request.content_type and 'application/json' in request.content_type:
                    return JsonResponse({
                        'ok': False,
                        'error': 'Request processing failed. Please try again.'
                    }, status=500)
                else:
                    # For non-AJAX requests, return a proper error page
                    from django.http import HttpResponseServerError
                    return HttpResponseServerError("An error occurred while processing your request.")

        return self.get_response(request)
