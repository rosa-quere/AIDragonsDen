from django import forms

from chat.models import Bot, Trigger


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

class ManageTriggersForm(forms.Form):
    triggers = forms.ModelMultipleChoiceField(
        queryset=Trigger.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label="Select Triggers",
    )
