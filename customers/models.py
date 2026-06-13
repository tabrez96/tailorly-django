import phonenumbers
from django.db import models
from django.core.exceptions import ValidationError

class Customer(models.Model):
    """
    A customer who places orders.
    """
    full_name = models.CharField(max_length=50)
    phone = models.CharField(max_length=20)
    country_code = models.CharField(max_length=2, default='IN')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.full_name

    def clean(self):
        """
        Run validation checks:
        * Check if the phone number is valid.

        Notes:
        * Mutates the phone number to be in E.164 format.
        """
        try:
            parsed = phonenumbers.parse(self.phone, self.country_code)
        except phonenumbers.NumberParseException:
            raise ValidationError({
                'phone': 'Could not recognize the phone number.'
            })

        if not phonenumbers.is_valid_number(parsed):
            raise ValidationError({
                'phone': 'Invalid phone number for the country.'
            })

        self.phone = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
