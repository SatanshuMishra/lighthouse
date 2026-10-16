import hmac

TOKEN_VARIABLE = "KILNROOM_TOKEN"

GUARDED = (
    ("POST", "/pieces"),
    ("DELETE", "/pieces/{id}"),
)


def requires_token(method, pattern):
    return (method, pattern) in GUARDED


def presented(headers, token):
    offered = headers.get("Authorization") or ""
    return token is not None and hmac.compare_digest(offered.encode("utf-8"), "Bearer {}".format(token).encode("utf-8"))
