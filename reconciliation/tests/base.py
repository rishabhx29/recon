from datetime import date
from decimal import Decimal

from django.test import TestCase

from reconciliation.models import CapitalCall, InvestorEntity, LineItem, Organization


class ReconTestCase(TestCase):
    def make_organization(self, slug='northwind', name=None):
        return Organization.objects.create(slug=slug, name=name or slug.title())

    def make_line_item(
        self,
        organization,
        reference,
        amount_called,
        investor_name='Probe Fund LLC',
        call_date=date(2026, 3, 25),
    ):
        investor, _ = InvestorEntity.objects.get_or_create(
            organization=organization, name=investor_name
        )
        capital_call, _ = CapitalCall.objects.get_or_create(
            organization=organization, call_date=call_date, due_date=date(2026, 4, 10)
        )
        return LineItem.objects.create(
            organization=organization,
            capital_call=capital_call,
            investor=investor,
            reference=reference,
            amount_called=Decimal(amount_called),
        )