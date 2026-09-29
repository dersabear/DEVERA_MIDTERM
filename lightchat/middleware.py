from urllib.parse import unquote, urlsplit, urlunsplit

from django.conf import settings
from django.urls import get_script_prefix, set_script_prefix


def normalize_script_name(value):
    value = value.strip() if isinstance(value, str) else ""
    if (
        not value
        or len(value) > 2048
        or not value.startswith("/")
        or any(char in value for char in "?#\\,")
        or any(ord(char) < 32 for char in value)
    ):
        return ""

    segments = []
    for segment in value.split("/"):
        if not segment:
            continue
        decoded = unquote(segment)
        if (
            decoded in {".", ".."}
            or "/" in decoded
            or "\\" in decoded
            or any(ord(char) < 32 for char in decoded)
        ):
            return ""
        segments.append(segment)
    return "/" + "/".join(segments) if segments else ""


def _deduplicate_configured_base(script_name, configured_base):
    if not configured_base:
        return script_name
    duplicate = f"{configured_base}{configured_base}"
    while script_name == duplicate or script_name.startswith(f"{duplicate}/"):
        script_name = script_name[len(configured_base):]
    return script_name


def resolve_script_name(meta, *, debug=None):
    configured_base = normalize_script_name(getattr(settings, "LIGHTCHAT_BASE_PATH", ""))
    script_name = normalize_script_name(meta.get("SCRIPT_NAME", ""))
    if script_name:
        return _deduplicate_configured_base(script_name, configured_base)
    debug_enabled = settings.DEBUG if debug is None else debug
    if debug_enabled:
        forwarded_prefix = normalize_script_name(meta.get("HTTP_X_FORWARDED_PREFIX", ""))
        if forwarded_prefix:
            return _deduplicate_configured_base(forwarded_prefix, configured_base)
    return configured_base


def _configured_base_fallback(meta):
    if normalize_script_name(meta.get("SCRIPT_NAME", "")):
        return ""
    debug_enabled = settings.DEBUG
    if debug_enabled and normalize_script_name(meta.get("HTTP_X_FORWARDED_PREFIX", "")):
        return ""
    return normalize_script_name(getattr(settings, "LIGHTCHAT_BASE_PATH", ""))


def _remove_configured_base_from_location(response, base_path):
    location = response.get("Location")
    if not base_path or not location:
        return

    try:
        parts = urlsplit(location)
    except ValueError:
        return
    if parts.scheme or parts.netloc:
        return
    path = parts.path
    while path == base_path or path.startswith(f"{base_path}/"):
        path = path[len(base_path):] or "/"
    if path != parts.path:
        response["Location"] = urlunsplit(("", "", path, parts.query, parts.fragment))


class ForwardedPrefixMiddleware:
    """Apply a request prefix and leave redirect prefixing to the configured proxy."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        script_name = resolve_script_name(request.META)
        if not script_name:
            return self.get_response(request)
        redirect_base = _configured_base_fallback(request.META)

        previous_prefix = get_script_prefix()
        request.META["SCRIPT_NAME"] = script_name
        path_info = request.path_info or "/"
        while path_info == script_name or path_info.startswith(f"{script_name}/"):
            path_info = path_info[len(script_name):] or "/"
            request.path_info = path_info
            request.META["PATH_INFO"] = path_info
        request.path = f"{script_name}{path_info}"
        set_script_prefix(f"{script_name}/")
        try:
            response = self.get_response(request)
            _remove_configured_base_from_location(response, redirect_base)
            return response
        finally:
            set_script_prefix(previous_prefix)
