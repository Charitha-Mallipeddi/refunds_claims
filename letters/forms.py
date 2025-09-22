from django import forms

REASONS = [
    ("insufficient_info", "Insufficient information"),
    ("invalid_ticket", "Invalid ticket"),
    ("outside_window", "Outside refund window"),
]

class LetterForm(forms.Form):
    customer_name = forms.CharField(label="Customer Name", max_length=120)  # required=True by default
    customer_email = forms.EmailField(label="Customer Email")
    reason = forms.ChoiceField(label="Denial Reason", choices=REASONS)
    notes = forms.CharField(label="Notes", widget=forms.Textarea, required=False)
