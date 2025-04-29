from django.core.management.base import BaseCommand
from django_q.tasks import schedule

from chat.models import Strategy


class Command(BaseCommand):
    help = "Setup the application"

    def add_arguments(self, parser):
        pass

    def handle(self, *args, **kwargs):
        # Populate database

        # Triggers
        trigger_names = ["general", "mention"]

        for name in trigger_names:
            Strategy.objects.get_or_create(name=name)
