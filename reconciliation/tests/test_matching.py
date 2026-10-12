from datetime import date
from decimal import Decimal

from reconciliation.models import BankTransaction
from reconciliation.services import match_transaction

from .base import ReconTestCase


class ReferenceMatchTests(ReconTestCase):
    def setUp(self):
        self.organization = self.make_organization()
        self.haller = self.make_line_item(
            self.organization, 'CC-1001', '27500.00', 'Haller Capital LLC'
        )

    def incoming(self, description, amount, bank_reference='FT1', on_date=date(2026, 4, 11)):
        return BankTransaction.objects.create(
            organization=self.organization,
            date=on_date,
            description=description,
            amount=Decimal(amount),
            type='credit',
            bank_reference=bank_reference,
        )

    def test_mangled_reference_matches(self):
        entry = self.incoming('ACH CREDIT HALLER CAPITAL cc1001', '20000.00')
        match_transaction(entry)
        entry.refresh_from_db()
        self.assertEqual(entry.status, 'suggested')
        self.assertEqual(entry.matches.get().line_item, self.haller)

    def test_partial_payment_is_still_a_match(self):
        entry = self.incoming('ACH CREDIT HALLER CAPITAL cc1001', '7500.00')
        match_transaction(entry)
        entry.refresh_from_db()
        self.assertEqual(entry.status, 'suggested')
        self.assertIn('partially pays', entry.matches.get().reason)

    def test_hyphenated_reference_in_the_description_is_found(self):
        entry = self.incoming('WIRE IN REF CC-1001', '27500.00')
        match_transaction(entry)
        entry.refresh_from_db()
        self.assertEqual(entry.matches.get().line_item, self.haller)

    def test_reference_in_the_bank_reference_column_also_matches(self):
        entry = self.incoming('WIRE INCOMING SOMETHING', '900.00', bank_reference='cc1001')
        match_transaction(entry)
        entry.refresh_from_db()
        self.assertEqual(entry.matches.get().line_item, self.haller)


class NameAndAmountTests(ReconTestCase):
    def setUp(self):
        self.organization = self.make_organization()
        self.patel = self.make_line_item(
            self.organization, 'CC-1003', '12500.00', 'Patel Family Trust'
        )

    def incoming(self, description, amount, on_date=date(2026, 4, 11)):
        return BankTransaction.objects.create(
            organization=self.organization,
            date=on_date,
            description=description,
            amount=Decimal(amount),
            type='credit',
            bank_reference='FT',
        )

    def test_name_and_exact_amount_match(self):
        entry = self.incoming('WIRE INCOMING PATEL FAMILY TRUST', '12500.00')
        match_transaction(entry)
        entry.refresh_from_db()
        self.assertEqual(entry.status, 'suggested')
        self.assertEqual(entry.matches.get().line_item, self.patel)

    def test_name_with_the_wrong_amount_does_not_match(self):
        entry = self.incoming('WIRE INCOMING PATEL FAMILY TRUST', '5000.00')
        match_transaction(entry)
        entry.refresh_from_db()
        self.assertEqual(entry.status, 'needs_review')
        self.assertEqual(entry.matches.count(), 0)

    def test_two_eligible_candidates_propose_both(self):
        first = self.make_line_item(
            self.organization, 'CC-1005', '15000.00', 'Oakridge Holdings LLC'
        )
        second = self.make_line_item(
            self.organization,
            'CC-1006',
            '15000.00',
            'Oakridge Holdings LLC',
            call_date=date(2026, 4, 1),
        )
        entry = self.incoming('WIRE INCOMING OAKRIDGE HOLDINGS LLC', '15000.00')
        match_transaction(entry)
        entry.refresh_from_db()
        self.assertEqual(entry.status, 'needs_review')
        self.assertEqual(
            set(entry.matches.values_list('line_item', flat=True)),
            {first.id, second.id},
        )
        self.assertEqual(entry.matches.filter(status='proposed').count(), 2)


class OverpaymentTests(ReconTestCase):
    def test_overpayment_produces_no_match_at_all(self):
        organization = self.make_organization()
        self.make_line_item(organization, 'CC-1003', '12500.00', 'Patel Family Trust')
        entry = BankTransaction.objects.create(
            organization=organization,
            date=date(2026, 4, 11),
            description='WIRE IN PATEL FAMILY TRUST CC-1003',
            amount=Decimal('13000.00'),
            type='credit',
            bank_reference='FT',
        )
        match_transaction(entry)
        entry.refresh_from_db()
        self.assertEqual(entry.status, 'needs_review')
        self.assertEqual(entry.matches.count(), 0)
        self.assertIn('exceeds remaining', entry.review_reason)


class EligibilityTests(ReconTestCase):
    def test_line_item_issued_after_the_payment_date_is_not_eligible(self):
        organization = self.make_organization()
        self.make_line_item(
            organization,
            'CC-1006',
            '15000.00',
            'Oakridge Holdings LLC',
            call_date=date(2026, 4, 1),
        )
        entry = BankTransaction.objects.create(
            organization=organization,
            date=date(2026, 3, 20),
            description='WIRE IN REF CC-1006',
            amount=Decimal('15000.00'),
            type='credit',
            bank_reference='FT',
        )
        match_transaction(entry)
        entry.refresh_from_db()
        self.assertNotIn(
            'CC-1006', entry.matches.values_list('line_item__reference', flat=True)
        )

    def test_reference_match_wins_over_a_name_match(self):
        organization = self.make_organization()
        self.make_line_item(organization, 'CC-1002', '25000.00', 'Rahul Shah Trust')
        entry = BankTransaction.objects.create(
            organization=organization,
            date=date(2026, 4, 11),
            description='WIRE IN RAHUL SHAH TRUST REF CC-1002',
            amount=Decimal('25000.00'),
            type='credit',
            bank_reference='FT',
        )
        match_transaction(entry)
        entry.refresh_from_db()
        self.assertEqual(entry.matches.count(), 1)
        self.assertTrue(entry.matches.get().reason.startswith('Reference CC-1002'))

    def test_fully_funded_line_item_drops_out(self):
        organization = self.make_organization()
        item = self.make_line_item(organization, 'CC-1003', '12500.00', 'Patel Family Trust')
        item.amount_funded = Decimal('12500.00')
        item.refresh_status()
        item.save()
        entry = BankTransaction.objects.create(
            organization=organization,
            date=date(2026, 4, 11),
            description='WIRE IN PATEL FAMILY TRUST',
            amount=Decimal('12500.00'),
            type='credit',
            bank_reference='FT',
        )
        match_transaction(entry)
        entry.refresh_from_db()
        self.assertEqual(entry.matches.count(), 0)