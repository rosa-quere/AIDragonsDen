from django import forms

from chat.models import Bot, Strategy, Segment, Settings


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

class ManageSettingsForm(forms.Form):
    settings = forms.ModelChoiceField(
        queryset=Settings.objects.all(),
        widget=forms.Select,
        label="Select Conversation Settings"
    )
    
class CreateSettingsForm(forms.ModelForm):
    class Meta:
        model = Settings
        fields = ['name', 'context', 'duration']
    
    def clean_name(self):
        name = self.cleaned_data['name']
        if Settings.objects.filter(name=name).exists():
            raise forms.ValidationError("A Settings instance with this name already exists.")
        return name

class CreateSegmentForm(forms.ModelForm):
    class Meta:
        model = Segment
        fields = ['name', 'prompt', 'duration_minutes', 'order', 'settings']