from django.http import HttpResponse 
from django.shortcuts import redirect

def unauthenticated_user(view_func):
    def wrapper_func(request,*args,**kwargs):
        if request.user.is_authenticated:
            return redirect("dashboard")
        else:
            return view_func(request,*args,**kwargs)
    return wrapper_func

def allowed_users(allowed=[]):
    def decorator(view_func):
        def wrapper_func(request,*args,**kwargs):
            groups = None
            if request.user.groups.exists():
                groups = request.user.groups.all()
                for group in groups:
                    if group.name in allowed:
                        return view_func(request,*args,**kwargs)
            return HttpResponse("You don't have premission to view this page!")
        return wrapper_func
    return decorator