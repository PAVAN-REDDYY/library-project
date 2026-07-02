from common.jwt_auth import encode_token, COOKIE_NAME


def issue_jwt_cookie(response, user):
    """Attach a signed JWT cookie to `response` after Django's own session
    login() has already run, so books-service/rentals-service can recognize
    this user via common.jwt_auth without any session state of their own.

    samesite='Lax' (not 'Strict') matters: Strict would stop the cookie being
    sent even on a plain top-level link click from another service's page,
    which would break "click Browse Books, still be logged in on books-service."
    """
    token = encode_token(user)
    response.set_cookie(COOKIE_NAME, token, httponly=True, samesite='Lax', max_age=12 * 3600)
    return response
