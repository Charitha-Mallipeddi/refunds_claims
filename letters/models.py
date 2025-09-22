from django.db import models

class Claim(models.Model):
    claim_id = models.CharField(max_length=50, unique=True)
    railroad = models.CharField(max_length=4, choices=[("LIRR","LIRR"),("MNR","MNR")])
    customer_name = models.CharField(max_length=200)
    customer_email = models.EmailField(blank=True)
    address1 = models.CharField(max_length=200, blank=True)
    address2 = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=40, blank=True)
    zip = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return f"{self.claim_id} – {self.customer_name}"
