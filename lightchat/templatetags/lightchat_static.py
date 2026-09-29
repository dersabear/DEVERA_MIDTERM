from urllib.parse import urlsplit

from django import template
from django.contrib.staticfiles.storage import staticfiles_storage


register = template.Library()


@register.simple_tag(takes_context=True)
def lightchat_static(context, path):
    url = staticfiles_storage.url(path)
    parsed = urlsplit(url)
    if parsed.scheme or parsed.netloc:
        return url

    request = context.get("request")
    script_name = request.META.get("SCRIPT_NAME", "").rstrip("/") if request else ""
    if not script_name or url.startswith(f"{script_name}/"):
        return url
    return f"{script_name}/{url.lstrip('/')}"
