from django import forms
from .models import *
from datetime import date

class EmployeeForm(forms.ModelForm):
    department = forms.CharField(required=False, widget=forms.TextInput(attrs={
        'class': 'form-control',
        'placeholder': 'Enter department'
    }))
    position = forms.CharField(required=False, widget=forms.TextInput(attrs={
        'class': 'form-control',
        'placeholder': 'Enter position'
    }))
    
    class Meta:
        model = Employee
        fields = ['name', 'email', 'phone', 'department', 'position', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter full name'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter email address'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter phone number'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }

class TimetableGenerationForm(forms.Form):
    month = forms.ChoiceField(
        choices=[(i, i) for i in range(1, 13)],
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    year = forms.ChoiceField(
        choices=[(i, i) for i in range(2020, 2031)],
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current_year = date.today().year
        self.fields['year'].initial = current_year
        self.fields['month'].initial = date.today().month

class TimeOffForm(forms.ModelForm):
    class Meta:
        model = TimeOff
        fields = ['employee', 'start_date', 'end_date', 'reason']
        widgets = {
            'employee': forms.Select(attrs={
                'class': 'form-select'
            }),
            'start_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control'
            }),
            'end_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control'
            }),
            'reason': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Enter reason for time off'
            }),
        }

class ShiftSwapRequestForm(forms.ModelForm):
    class Meta:
        model = ShiftSwapRequest
        fields = ['requested_to', 'requested_date', 'reason']
        widgets = {
            'requested_to': forms.Select(attrs={
                'class': 'form-select'
            }),
            'requested_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control'
            }),
            'reason': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Enter reason for swap request'
            }),
        }

class FoodPickupScheduleForm(forms.ModelForm):
    class Meta:
        model = FoodPickupSchedule
        fields = ['date', 'max_people']
        widgets = {
            'date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control'
            }),
            'max_people': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'max': 10
            }),
        }

# Remove or comment out the old LunchScheduleForm
# class LunchScheduleForm(forms.ModelForm):
#     class Meta:
#         model = LunchSchedule
#         fields = ['date', 'time_slot', 'max_people']
#         widgets = {
#             'date': forms.DateInput(attrs={
#                 'type': 'date',
#                 'class': 'form-control'
#             }),
#             'time_slot': forms.TimeInput(attrs={
#                 'type': 'time',
#                 'class': 'form-control'
#             }),
#             'max_people': forms.NumberInput(attrs={
#                 'class': 'form-control'
#             }),
#         }