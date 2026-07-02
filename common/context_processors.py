"""
Cross-service navigation needs a real host:port, not a root-relative path,
because there is no gateway unifying the three services under one origin -
each runs standalone (e.g. users-service on :8001, books-service on :8002,
rentals-service on :8003). A link like `/accounts/login/` only resolves
correctly if the browser happens to already be on users-service's origin;
from books-service or rentals-service it would 404 against the wrong app.

So every cross-service template link uses one of these three, e.g.
`{{ USERS_URL }}/accounts/login/`, never a bare root-relative path. Same-
service links keep using {% url %} as normal - only cross-service ones need
this. If a deployment later adds a gateway/reverse proxy, these three
settings just need overriding to match (see each service's settings.py).
"""
from django.conf import settings


def service_urls(request):
    return {
        'USERS_URL': settings.USERS_SERVICE_PUBLIC_URL,
        'BOOKS_URL': settings.BOOKS_SERVICE_PUBLIC_URL,
        'RENTALS_URL': settings.RENTALS_SERVICE_PUBLIC_URL,
    }
