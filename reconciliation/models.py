from decimal import Decimal

from django.db import models


class Organization(models.Model):
    # the X-Organization header carries this, not the display name
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=200)

    def __str__(self):
        return self.name


class InvestorEntity(models.Model):
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='investors'
    )
    # the legal entity name the bank puts in wire descriptions
    name = models.CharField(max_length=200)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['organization', 'name'], name='unique_investor_name_per_org'
            ),
        ]

    def __str__(self):
        return self.name


class CapitalCall(models.Model):
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='capital_calls'
    )
    call_date = models.DateField()
    due_date = models.DateField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['organization', 'call_date', 'due_date'],
                name='unique_call_dates_per_org',
            ),
        ]

    def __str__(self):
        return f'call {self.call_date}, due {self.due_date}'


class LineItem(models.Model):
    OPEN = 'open'
    PARTIALLY_FUNDED = 'partially_funded'
    FUNDED = 'funded'
    STATUS_CHOICES = [
        (OPEN, 'Open'),
        (PARTIALLY_FUNDED, 'Partially funded'),
        (FUNDED, 'Funded'),
    ]

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='line_items'
    )
    capital_call = models.ForeignKey(
        CapitalCall, on_delete=models.CASCADE, related_name='line_items'
    )
    investor = models.ForeignKey(
        InvestorEntity, on_delete=models.CASCADE, related_name='line_items'
    )
    # what LPs are told to put in the wire reference. deliberately not unique:
    # one code can sit on two calls and matching has to cope with that
    reference = models.CharField(max_length=50)
    amount_called = models.DecimalField(max_digits=14, decimal_places=2)
    amount_funded = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0.00')
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=OPEN)

    @property
    def remaining(self):
        return self.amount_called - self.amount_funded

    def refresh_status(self):
        if self.remaining <= 0:
            self.status = self.FUNDED
        elif self.amount_funded > 0:
            self.status = self.PARTIALLY_FUNDED
        else:
            self.status = self.OPEN
        return self

    def __str__(self):
        return f'{self.reference} {self.investor.name}'
