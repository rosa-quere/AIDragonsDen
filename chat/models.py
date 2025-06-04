import uuid

from django.contrib.auth.models import User
from django.db import models
from django.urls import reverse


class Bot(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    color = models.CharField(max_length=18, default="#cd5334ff")
    model = models.CharField(max_length=255)
    prompt = models.TextField()
    temperature = models.FloatField(default=0.8)

    def __str__(self):
        return f"Bot {self.id} {self.name} ({self.model})"


class Strategy(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    triggered_at = models.DateTimeField(null=True, blank=True, default=None)

    def __str__(self):
        return f"{self.name}"
    
class SubTopic(models.Model):
    STATUS_CHOICES = (
        ("being discussed", "Being Discussed"),
        ("well discussed", "Well Discussed"),
        ("not discussed", "Not Discussed")
    )
    name = models.CharField(max_length=255)
    status = models.CharField(max_length=25, choices=STATUS_CHOICES)
    status_updated_at = models.DateTimeField(auto_now=True)
    conversation = models.ForeignKey("Conversation", on_delete=models.CASCADE, related_name="sub_topics", null=True,  blank=True)
    
    def __str__(self):
        return f"{self.name}, {self.status}"

class Segment(models.Model):
    id = models.AutoField(primary_key=True)
    settings = models.ForeignKey("Settings", null=True, blank=True, on_delete=models.CASCADE, related_name='segments')
    name = models.CharField(max_length=100, null=True, blank=True)
    prompt = models.TextField(blank=True, null=True)
    order = models.PositiveIntegerField()
    duration_minutes = models.PositiveIntegerField()
    
    def __str__(self):
        return f"{self.name} ({self.duration_minutes} min)"

    class Meta:
        ordering = ['order']

class Settings(models.Model):
    name = models.CharField(max_length=255, unique=True)
    context = models.TextField(blank=True, null=True)
    duration = models.PositiveIntegerField(null=True, blank=True)
    
    def __str__(self):
        return self.name
    
class Conversation(models.Model):
    id = models.AutoField(primary_key=True)
    uuid = models.UUIDField(default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255, blank=True, null=True, default="New Conversation")
    creation_date = models.DateTimeField(auto_now_add=True)
    title_update_date = models.DateTimeField(auto_now=True)
    participants = models.ManyToManyField("Participant", related_name="conversations")
    count_old_participants = models.PositiveIntegerField(default=0)
    strategies = models.ManyToManyField(Strategy, related_name="conversations", blank=True)
    summary = models.CharField(max_length=255, blank=True, null=True)
    summary_update_date = models.DateTimeField(auto_now=True)
    summary_posted_date = models.DateTimeField(auto_now=True)
    subtopics_updated_at = models.DateTimeField(auto_now=True)
    settings = models.ForeignKey(Settings, null=True, blank=True, on_delete=models.SET_NULL, related_name="conversations")
    

    def __str__(self):
        return f"Conversation {self.uuid} created on {self.creation_date}"

    def list_of_bots(self):
        return ", ".join([participant.name() for participant in self.participants.filter(participant_type="bot")])

    def list_of_humans(self):
        return ", ".join([participant.name() for participant in self.participants.filter(participant_type="user")])
    
    @property
    def invite_link(self):
        return reverse("chat:join_conversation", kwargs={"conversation_uuid": self.uuid})


class Participant(models.Model):
    PARTICIPANT_TYPE_CHOICES = (
        ("user", "User"),
        ("bot", "Bot"),
    )

    id = models.AutoField(primary_key=True)
    is_temporary = models.BooleanField(default=False)
    participant_type = models.CharField(max_length=10, choices=PARTICIPANT_TYPE_CHOICES)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="participant_user",
    )
    bot = models.ForeignKey(
        Bot,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="participant_bot",
    )

    def __str__(self):
        return f"Participant ({self.participant_type}) - {'User: ' + self.user.username if self.user else 'Bot: ' + self.bot.name}"

    def name(self):
        return self.user.username if self.participant_type == "user" else self.bot.name


class Message(models.Model):
    id = models.AutoField(primary_key=True)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    participant = models.ForeignKey(Participant, on_delete=models.CASCADE, related_name="sent_messages")
    timestamp = models.DateTimeField(auto_now_add=True)
    triggered_bots = models.ManyToManyField(Bot, related_name="responded_messages", blank=True)
    message = models.TextField()

    def __str__(self):
        return f"Message from {self.participant} at {self.timestamp} in conversation {self.conversation.uuid}"

    def participant_name(self):
        return self.participant.user.username if self.participant.participant_type == "user" else self.participant.bot.name


class LLMRequest(models.Model):
    id = models.AutoField(primary_key=True)
    request_type = models.CharField(max_length=255)
    model = models.CharField(max_length=255)
    temperature = models.FloatField()
    timestamp = models.DateTimeField(auto_now_add=True)
    prompt = models.TextField()
    response = models.TextField()
    total_tokens = models.IntegerField(editable=False, default=0)
    completion_tokens = models.IntegerField(editable=False, default=0)

    def __str__(self):
        return f"LLMRequest {self.id} at {self.timestamp}"