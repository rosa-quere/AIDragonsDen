from django.db.models.signals import post_save
from django.dispatch import receiver
from django_q.models import Schedule, Task
from django_q.tasks import async_task
from django.core.cache import cache
from chat.models import Message
import logging

logger = logging.getLogger(__name__)

@receiver(post_save, sender=Message)
def on_message_created(sender, instance, created, **kwargs):
    if not created:
        return

    conversation = instance.conversation
    schedule_name = f"generate_messages_{conversation.uuid}"

    # Cancel any previously scheduled task for this conversation
    gen_tasks = Task.objects.filter(name=schedule_name)
    if gen_tasks:
        for task in gen_tasks:
            task.delete()
        logger.info(f"[INFO] Cancelling existing scheduled task for {schedule_name}")
    
    # Cancel any previously scheduled task for this conversation
    chime_tasks = Schedule.objects.filter(name=f"chime_fallback_{conversation.id}")
    if chime_tasks:
        for task in chime_tasks:
            task.delete()
        logger.info(f"[INFO] Cancelled fallback chime task for conversation {conversation.id} due to new message")
    
    # fallback_cache_key = f"fallback_chime_{conversation.id}"
    # if cache.get(fallback_cache_key):
    #     cache.delete(fallback_cache_key)
    #     logger.info(f"[INFO] Cancelled fallback chime task for conversation {conversation.id} due to new message")

    # Trigger a new async task
    logger.info(f"[INFO] Triggering new generate_messages task for {conversation.uuid}")
    async_task("chat.tasks.generate_messages", conversation.id, task_name=schedule_name)