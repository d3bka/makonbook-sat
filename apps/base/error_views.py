from django.shortcuts import render


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


def makon_error_page(request, exception=None, status_code=404, **kwargs):
    details = ERROR_MESSAGES.get(status_code, ERROR_MESSAGES[404]).copy()
    return render(
        request,
        "errors/makon_error.html",
        {
            "status_code": status_code,
            "error_title": details["title"],
            "error_headline": details["headline"],
            "error_message": details["message"],
            "exception": exception,
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
