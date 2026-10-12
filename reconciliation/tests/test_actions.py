from datetime import date
from decimal import Decimal

from rest_framework.test import APIClient

from reconciliation.models import BankTransaction, Match
from reconciliation.services import match_transaction

from .base import ReconTestCase


class ActionTestCase(ReconTestCase):
    def setUp(self):
        self.organization = self.make_organization()
        self.client = APIClient()
        self.item = self.make_line_item(
            self.organization, 'CC-1001', '10000.00', 'Haller Capital LLC'
        )
        self.entry = self.incoming('WIRE IN REF CC-1001', '4000.00', 'FT1')
        match_transaction(self.entry)
        self.match = self.entry.matches.get()

    def incoming(self, description, amount, bank_reference):
        return BankTransaction.objects.create(
            organization=self.organization,
            date=date(2026, 4, 11),
            description=description,
            amount=Decimal(amount),
            type='credit',
            bank_reference=bank_reference,
        )

    def approve(self, match=None):
        return self.client.post(
            f'/api/matches/{(match or self.match).id}/approve',
            HTTP_X_ORGANIZATION='northwind',
        )

    def reject(self, match=None):
        return self.client.post(
            f'/api/matches/{(match or self.match).id}/reject',
            HTTP_X_ORGANIZATION='northwind',
        )

    def ignore(self, entry=None):
        return self.client.post(
            f'/api/transactions/{(entry or self.entry).id}/ignore',
            HTTP_X_ORGANIZATION='northwind',
        )


class ApproveTests(ActionTestCase):
    def test_approve_adds_the_amount_and_leaves_the_rest_outstanding(self):
        self.assertEqual(self.approve().status_code, 200)
        self.item.refresh_from_db()
        self.entry.refresh_from_db()
        self.match.refresh_from_db()
        self.assertEqual(self.item.amount_funded, Decimal('4000.00'))
        self.assertEqual(self.item.remaining, Decimal('6000.00'))
        self.assertEqual(self.item.status, 'partially_funded')
        self.assertEqual(self.match.status, 'approved')
        self.assertEqual(self.entry.status, 'reconciled')

    def test_second_approval_is_refused_and_does_not_fund_twice(self):
        self.approve()
        self.assertEqual(self.approve().status_code, 409)
        self.item.refresh_from_db()
        self.assertEqual(self.item.amount_funded, Decimal('4000.00'))

    def test_approval_is_refused_when_remaining_no_longer_covers_it(self):
        self.item.amount_funded = Decimal('8000.00')
        self.item.refresh_status()
        self.item.save()
        self.assertEqual(self.approve().status_code, 409)
        self.item.refresh_from_db()
        self.assertEqual(self.item.amount_funded, Decimal('8000.00'))

    def test_approving_one_candidate_rejects_the_others(self):
        other_item = self.make_line_item(
            self.organization,
            'CC-1002',
            '4000.00',
            'Oakridge Holdings LLC',
            call_date=date(2026, 4, 1),
        )
        other = Match.objects.create(
            organization=self.organization,
            transaction=self.entry,
            line_item=other_item,
            status=Match.PROPOSED,
            reason='second candidate',
        )
        self.approve()
        other.refresh_from_db()
        other_item.refresh_from_db()
        self.assertEqual(other.status, 'rejected')
        self.assertEqual(other_item.amount_funded, Decimal('0.00'))


class RejectTests(ActionTestCase):
    def test_rejecting_the_last_match_returns_the_transaction_to_review(self):
        self.reject()
        self.entry.refresh_from_db()
        self.match.refresh_from_db()
        self.item.refresh_from_db()
        self.assertEqual(self.match.status, 'rejected')
        self.assertEqual(self.entry.status, 'needs_review')
        self.assertEqual(self.item.amount_funded, Decimal('0.00'))

    def test_an_approved_match_cannot_be_rejected(self):
        self.approve()
        self.assertEqual(self.reject().status_code, 409)


class IgnoreTests(ActionTestCase):
    def test_ignore_rejects_the_matches_and_funds_nothing(self):
        self.assertEqual(self.ignore().status_code, 200)
        self.entry.refresh_from_db()
        self.match.refresh_from_db()
        self.item.refresh_from_db()
        self.assertEqual(self.entry.status, 'ignored')
        self.assertEqual(self.match.status, 'rejected')
        self.assertEqual(self.item.amount_funded, Decimal('0.00'))

    def test_a_reconciled_transaction_cannot_be_ignored(self):
        self.approve()
        self.assertEqual(self.ignore().status_code, 409)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.status, 'reconciled')


class IsolationTests(ReconTestCase):
    def setUp(self):
        self.northwind = self.make_organization('northwind')
        self.bluebird = self.make_organization('bluebird')
        self.client = APIClient()

    def test_listing_never_returns_another_organizations_rows(self):
        BankTransaction.objects.create(
            organization=self.bluebird,
            date=date(2026, 4, 11),
            description='BLUEBIRD WIRE',
            amount=Decimal('100.00'),
            type='credit',
            bank_reference='FT-BLUE',
        )
        response = self.client.get('/api/transactions', HTTP_X_ORGANIZATION='northwind')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['results'], [])

    def test_approving_another_organizations_match_is_not_found(self):
        item = self.make_line_item(
            self.bluebird, 'CC-2001', '5000.00', 'Cedar Grove Fund LP'
        )
        entry = BankTransaction.objects.create(
            organization=self.bluebird,
            date=date(2026, 4, 11),
            description='WIRE IN REF CC-2001',
            amount=Decimal('100.00'),
            type='credit',
            bank_reference='FT-BLUE',
        )
        match = Match.objects.create(
            organization=self.bluebird,
            transaction=entry,
            line_item=item,
            status=Match.PROPOSED,
            reason='test',
        )
        response = self.client.post(
            f'/api/matches/{match.id}/approve', HTTP_X_ORGANIZATION='northwind'
        )
        self.assertEqual(response.status_code, 404)
        item.refresh_from_db()
        self.assertEqual(item.amount_funded, Decimal('0.00'))

    def test_missing_header_is_a_bad_request(self):
        self.assertEqual(self.client.get('/api/transactions').status_code, 400)

    def test_unknown_organization_is_not_found(self):
        response = self.client.get('/api/transactions', HTTP_X_ORGANIZATION='ghost')
        self.assertEqual(response.status_code, 404)