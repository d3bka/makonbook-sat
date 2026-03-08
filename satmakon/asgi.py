"""
ASGI config for sat800makon project.

It exposes the ASGI callable as a module-level variable named ``application``.g

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application 

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'satmakon.settings')

application = get_asgi_application()
