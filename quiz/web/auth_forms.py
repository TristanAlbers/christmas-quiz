from django import forms


class TeamLoginForm(forms.Form):
    team = forms.ChoiceField(choices=(("a", "Team A"), ("b", "Team B")))
    pin = forms.CharField(widget=forms.PasswordInput, strip=False)


class AdminLoginForm(forms.Form):
    username = forms.CharField(max_length=150)
    password = forms.CharField(widget=forms.PasswordInput, strip=False)
