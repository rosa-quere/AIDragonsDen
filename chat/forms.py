from django import forms

from chat.models import Bot, Strategy, Conversation


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

class ManageContextForm(forms.ModelForm):
    class Meta:
        model = Conversation
        fields = ['context']
        widgets = {
            'context': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3, 
                'placeholder': 'e.g., This conversation simulates a Dragon\'s Den scenario with three chatbot "Dragons" acting as expert investors and one user acting as the interviewed entrepreneur.'})
        }
