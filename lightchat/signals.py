from django.core.files.storage import default_storage
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import Attachment


@receiver(post_delete, sender=Attachment)
def remove_attachment_file(sender, instance, **kwargs):
    if instance.file and default_storage.exists(instance.file.name):
        default_storage.delete(instance.file.name)
