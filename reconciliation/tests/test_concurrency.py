from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from threading import Barrier

from django.db import close_old_connections
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from reconciliation.models import (
    BankTransaction,
    CapitalCall,
    InvestorEntity,
    LineItem,
    Match,
    Organization,
)


class ConcurrentApprovalTests(TransactionTestCase):
    """TransactionTestCase, not TestCase: the latter wraps each test in a
    transaction the worker threads cannot see, so both requests would fail for
    the wrong reason and the test would pass without proving anything."""

    def setUp(self):
        self.organization = Organization.objects.create(
            slug='northwind', name='Northwind Ventures'
        )
        investor = InvestorEntity.objects.create(
            organization=self.organization, name='Haller Capital LLC'
        )
        capital_call = CapitalCall.objects.create(
            organization=self.organization,
            call_date=date(2026, 3, 25),
            due_date=date(2026, 4, 10),
        )
        self.line_item = LineItem.objects.create(
            organization=self.organization,
            capital_call=capital_call,
            investor=investor,
            reference='CC-1001',
            amount_called=Decimal('10000.00'),
        )

    def wire(self, bank_reference, amount):
        return BankTransaction.objects.create(
            organization=self.organization,
            date=date(2026, 4, 11),
            description='WIRE IN REF CC-1001',
            amount=Decimal(amount),
            type='credit',
            bank_reference=bank_reference,
        )

    def propose(self, bank_reference, amount):
        return Match.objects.create(
            organization=self.organization,
            transaction=self.wire(bank_reference, amount),
            line_item=self.line_item,
            status=Match.PROPOSED,
            reason='candidate',
        )

    def approve_all(self, match_ids):
        gate = Barrier(len(match_ids))

        def approve(match_id):
            close_old_connections()
            gate.wait()
            client = APIClient()
            response = client.post(
                f'/api/matches/{match_id}/approve',
                HTTP_X_ORGANIZATION='northwind',
            )
            close_old_connections()
            return response.status_code

        with ThreadPoolExecutor(max_workers=len(match_ids)) as pool:
            return list(pool.map(approve, match_ids))

    def test_the_same_approval_twice_funds_the_line_item_once(self):
        first = self.propose('FT1', '4000.00')
        statuses = self.approve_all([first.id, first.id])

        self.assertEqual(sorted(statuses), [200, 409])
        self.line_item.refresh_from_db()
        self.assertEqual(self.line_item.amount_funded, Decimal('4000.00'))

    def test_two_wires_that_together_exceed_the_line_item_cannot_both_land(self):
        # 8000 fits inside 10000, but only once. the loser has to re-read the
        # line item after the lock and find 2000 left
        first = self.propose('FT1', '8000.00')
        second = self.propose('FT2', '8000.00')
        statuses = self.approve_all([first.id, second.id])

        self.assertEqual(sorted(statuses), [200, 409])
        self.line_item.refresh_from_db()
        self.assertEqual(self.line_item.amount_funded, Decimal('8000.00'))