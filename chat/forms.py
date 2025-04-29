from django import forms

from chat.models import Bot, Strategy


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
