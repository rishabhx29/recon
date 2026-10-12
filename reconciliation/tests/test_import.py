from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command

from reconciliation.models import BankTransaction, LineItem, Organization
from reconciliation.services import import_statement, parse_statement

from .base import ReconTestCase

HEADER = 'date,description,amount,type,reference\n'


def csv_file(*rows):
    return SimpleUploadedFile('statement.csv', (HEADER + ''.join(rows)).encode())


class MissingColumnTests(ReconTestCase):
    def test_whole_file_rejected_and_nothing_saved(self):
        upload = SimpleUploadedFile(
            'statement.csv',
            b'date,description,amount,type\n2026-04-03,WIRE,1.00,credit\n',
        )
        with self.assertRaises(Exception) as raised:
            import_statement(upload, self.make_organization())
        self.assertIn('missing column: reference', str(raised.exception))
        self.assertEqual(BankTransaction.objects.count(), 0)


class AmountParsingTests(ReconTestCase):
    def setUp(self):
        self.organization = self.make_organization()

    def test_thousands_separator_stores_an_exact_decimal(self):
        # the separator has to be inside a quoted field. unquoted, csv splits the
        # row and the amount arrives as '25' with '000.00' landing on type
        import_statement(csv_file('2026-04-03,WIRE,"25,000.00",credit,FT1\n'), self.organization)
        stored = BankTransaction.objects.get()
        self.assertEqual(stored.amount, Decimal('25000.00'))
        self.assertIsInstance(stored.amount, Decimal)

    def test_an_unquoted_separator_is_reported_as_a_bad_row_not_imported(self):
        summary = import_statement(
            csv_file('2026-04-03,WIRE,25,000.00,credit,FT1\n'), self.organization
        )
        self.assertEqual(summary['imported'], 0)
        self.assertEqual(summary['errors'][0]['line'], 2)
        self.assertEqual(BankTransaction.objects.count(), 0)

    def test_credit_with_negative_amount_is_reported(self):
        _, errors = parse_statement(csv_file('2026-04-03,WIRE,-100.00,credit,FT1\n'))
        self.assertEqual(errors, [{'line': 2, 'message': 'credits must be positive'}])
        self.assertEqual(BankTransaction.objects.count(), 0)

    def test_debit_with_positive_amount_is_reported(self):
        _, errors = parse_statement(csv_file('2026-04-03,FEE,100.00,debit,FT1\n'))
        self.assertEqual(errors, [{'line': 2, 'message': 'debits must be negative'}])

    def test_impossible_calendar_date_is_reported_with_its_line(self):
        _, errors = parse_statement(csv_file('2026-04-31,WIRE,100.00,credit,FT1\n'))
        self.assertEqual(errors, [{'line': 2, 'message': 'invalid date: 2026-04-31'}])

    def test_zero_is_rejected(self):
        _, errors = parse_statement(csv_file('2026-04-03,WIRE,0.00,credit,FT1\n'))
        self.assertEqual(errors[0]['message'], 'amount cannot be zero')

    def test_amount_wider_than_the_column_is_reported_not_raised(self):
        # the column is numeric(14, 2); an oversized amount must not take the
        # whole import down with a database error
        summary = import_statement(
            csv_file(
                '2026-04-03,WIRE,100.00,credit,FT1\n',
                '2026-04-04,WIRE,999999999999999999999.00,credit,FT2\n',
                '2026-04-05,WIRE,200.00,credit,FT3\n',
            ),
            self.organization,
        )
        self.assertEqual(summary['imported'], 2)
        self.assertIn('amount out of range', summary['errors'][0]['message'])


class ValidAndInvalidTogetherTests(ReconTestCase):
    def test_valid_rows_import_while_invalid_ones_are_reported(self):
        organization = self.make_organization()
        summary = import_statement(
            csv_file(
                '2026-04-03,WIRE,100.00,credit,FT1\n',
                '2026-04-31,WIRE,100.00,credit,FT2\n',
                '2026-04-04,WIRE,200.00,credit,FT3\n',
            ),
            organization,
        )
        self.assertEqual(summary['imported'], 2)
        self.assertEqual(summary['errors'][0]['line'], 3)
        self.assertEqual(
            sorted(BankTransaction.objects.values_list('amount', flat=True)),
            [Decimal('100.00'), Decimal('200.00')],
        )


class DuplicateTests(ReconTestCase):
    def setUp(self):
        self.organization = self.make_organization()
        self.rows = '2026-04-03,WIRE,100.00,credit,FT1\n'

    def test_reupload_counts_every_row_as_duplicate(self):
        import_statement(csv_file(self.rows), self.organization)
        again = import_statement(csv_file(self.rows), self.organization)
        self.assertEqual(again['imported'], 0)
        self.assertEqual(again['duplicates'], 1)
        self.assertEqual(BankTransaction.objects.count(), 1)

    def test_duplicate_inside_one_file_is_skipped(self):
        summary = import_statement(
            csv_file(
                '2026-04-03,WIRE,100.00,credit,FT1\n',
                '2026-04-04,WIRE,100.00,credit,FT1\n',
            ),
            self.organization,
        )
        self.assertEqual(summary['imported'], 1)
        self.assertEqual(summary['duplicate_lines'], [3])
        self.assertEqual(BankTransaction.objects.count(), 1)

    def test_two_organizations_may_hold_the_same_bank_reference(self):
        bluebird = self.make_organization('bluebird')
        import_statement(csv_file(self.rows), self.organization)
        summary = import_statement(csv_file(self.rows), bluebird)
        self.assertEqual(summary['imported'], 1)
        self.assertEqual(BankTransaction.objects.count(), 2)


class DebitTests(ReconTestCase):
    def test_debit_is_stored_as_ignored_with_a_negative_amount(self):
        organization = self.make_organization()
        import_statement(csv_file('2026-04-03,BANK FEE,-25.00,debit,FEE1\n'), organization)
        stored = BankTransaction.objects.get()
        self.assertEqual(stored.status, 'ignored')
        self.assertEqual(stored.amount, Decimal('-25.00'))
        self.assertEqual(stored.matches.count(), 0)


class SeedCommandTests(ReconTestCase):
    def test_running_it_twice_creates_no_duplicates(self):
        call_command('seed_demo')
        call_command('seed_demo')
        self.assertEqual(Organization.objects.count(), 2)
        self.assertEqual(LineItem.objects.count(), 7)