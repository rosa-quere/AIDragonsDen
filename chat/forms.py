from django import forms
from django.forms import inlineformset_factory

from chat.models import Bot, Strategy, Conversation, Segment


class ManageBotsForm(forms.Form):
    bots = forms.ModelMultipleChoiceField(
        queryset=Bot.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label="Select Bots",
    )

class CreateBotForm(forms.ModelForm):
    class Meta:
        model = Bot
        fields = ['name', 'description', 'color', 'model', 'prompt', 'temperature']

class ManageStrategiesForm(forms.Form):
    strategies = forms.ModelMultipleChoiceField(
        queryset=Strategy.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label="Select Strategies",
    )

class ManageConversationForm(forms.ModelForm):
    class Meta:
        model = Conversation
        fields = ['context', 'duration']

SegmentFormSet = inlineformset_factory(
    Conversation,
    Segment,
    fields=('name', 'prompt', 'duration_minutes', 'order'),
    extra=1,
    can_delete=True
)
