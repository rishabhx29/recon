from decimal import Decimal

from django.db import models


class Organization(models.Model):
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=200)

    def __str__(self):
        return self.name


class InvestorEntity(models.Model):
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='investors'
    )
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
    # one code can sit on two calls, so this is deliberately not unique
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


class BankTransaction(models.Model):
    CREDIT = 'credit'
    DEBIT = 'debit'
    TYPE_CHOICES = [
        (CREDIT, 'Credit'),
        (DEBIT, 'Debit'),
    ]

    SUGGESTED = 'suggested'
    NEEDS_REVIEW = 'needs_review'
    RECONCILED = 'reconciled'
    IGNORED = 'ignored'
    STATUS_CHOICES = [
        (SUGGESTED, 'Suggested'),
        (NEEDS_REVIEW, 'Needs review'),
        (RECONCILED, 'Reconciled'),
        (IGNORED, 'Ignored'),
    ]

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='transactions'
    )
    date = models.DateField()
    description = models.TextField()
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    bank_reference = models.CharField(max_length=100)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=NEEDS_REVIEW
    )
    review_reason = models.TextField(blank=True)

    class Meta:
        ordering = ['-date', '-id']
        constraints = [
            models.UniqueConstraint(
                fields=['organization', 'bank_reference'],
                name='unique_bank_reference_per_org',
            ),
        ]

    def __str__(self):
        return f'{self.date} {self.bank_reference} {self.amount}'


class Match(models.Model):
    PROPOSED = 'proposed'
    APPROVED = 'approved'
    REJECTED = 'rejected'
    STATUS_CHOICES = [
        (PROPOSED, 'Proposed'),
        (APPROVED, 'Approved'),
        (REJECTED, 'Rejected'),
    ]

    # denormalized so a match lookup is scoped without joining through it
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='matches'
    )
    transaction = models.ForeignKey(
        BankTransaction, on_delete=models.CASCADE, related_name='matches'
    )
    line_item = models.ForeignKey(
        LineItem, on_delete=models.CASCADE, related_name='matches'
    )
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default=PROPOSED
    )
    reason = models.TextField()

    def __str__(self):
        return f'{self.transaction_id} -> {self.line_item_id} ({self.status})'
