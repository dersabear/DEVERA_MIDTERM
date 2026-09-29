from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm

from .models import ChatSession, Feedback, MemoryItem, UserSettings

User = get_user_model()


class RegistrationForm(UserCreationForm):
    display_name = forms.CharField(max_length=80)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username",)


class ProfileForm(forms.Form):
    username = forms.CharField(max_length=150)
    display_name = forms.CharField(max_length=80)

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        self.fields["username"].initial = user.username
        self.fields["display_name"].initial = user.lightchat_profile.display_name

    def clean_username(self):
        username = self.cleaned_data["username"]
        if User.objects.exclude(pk=self.user.pk).filter(username__iexact=username).exists():
            raise forms.ValidationError("That username is already in use.")
        return username


class GlobalPromptForm(forms.ModelForm):
    class Meta:
        model = UserSettings
        fields = ("global_system_prompt",)
        widgets = {"global_system_prompt": forms.Textarea(attrs={"rows": 5, "maxlength": 4000})}


class MemoryItemForm(forms.ModelForm):
    class Meta:
        model = MemoryItem
        fields = ("content", "enabled")
        widgets = {"content": forms.TextInput(attrs={"maxlength": 500})}


class ChatRenameForm(forms.ModelForm):
    class Meta:
        model = ChatSession
        fields = ("title",)


class ChatInstructionsForm(forms.ModelForm):
    class Meta:
        model = ChatSession
        fields = ("system_instructions",)
        widgets = {"system_instructions": forms.Textarea(attrs={"rows": 4, "maxlength": 4000})}


class FeedbackForm(forms.ModelForm):
    class Meta:
        model = Feedback
        fields = ("rating", "comment")
