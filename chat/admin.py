from django.contrib import admin

from chat.models import Bot, Conversation, LLMRequest, Message, Participant, Strategy, SubTopic, Segment, Settings

class LLMRequestAdmin(admin.ModelAdmin):
    readonly_fields = ("total_tokens", "completion_tokens")


admin.site.register(Conversation)
admin.site.register(Participant)
admin.site.register(Bot)
admin.site.register(Message)
admin.site.register(Strategy)
admin.site.register(SubTopic)
admin.site.register(LLMRequest, LLMRequestAdmin)
admin.site.register(Segment)
admin.site.register(Settings)
