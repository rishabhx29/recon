import csv
import io
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import F
from rest_framework import exceptions

from .errors import Conflict
from .models import BankTransaction, LineItem, Match

REQUIRED_COLUMNS = ['date', 'description', 'amount', 'type', 'reference']
SUFFIXES = ('LLC', 'LP', 'LTD', 'INC')


class MissingColumns(Exception):
    # the file is unusable, as opposed to a bad row which is skipped
    pass


class RowError(Exception):
    pass


def read_header(uploaded_file):
    # utf-8-sig eats the byte order mark Excel leaves at the start of a csv
    reader = csv.reader(
        io.TextIOWrapper(uploaded_file, encoding='utf-8-sig', newline='')
    )
    header = next(reader, None)
    if header is None:
        raise MissingColumns('file is empty')

    header = [column.strip().lower() for column in header]
    missing = [column for column in REQUIRED_COLUMNS if column not in header]
    if missing:
        raise MissingColumns(f"missing column: {', '.join(missing)}")

    return reader, {column: header.index(column) for column in REQUIRED_COLUMNS}


@dataclass
class StatementRow:
    line: int
    date: date
    description: str
    amount: Decimal
    type: str
    bank_reference: str


def parse_row(raw, index, line):
    date_text = raw[index['date']].strip()
    description = raw[index['description']].strip()
    amount_text = raw[index['amount']].strip()
    entry_type = raw[index['type']].strip().lower()
    bank_reference = raw[index['reference']].strip()

    if not description:
        raise RowError('description is required')
    if not bank_reference:
        raise RowError('reference is required')

    try:
        value_date = datetime.strptime(date_text, '%Y-%m-%d').date()
    except ValueError:
        raise RowError(f'invalid date: {date_text}') from None

    if entry_type not in (BankTransaction.CREDIT, BankTransaction.DEBIT):
        raise RowError(f'invalid type: {entry_type}')

    try:
        amount = Decimal(amount_text.replace(',', ''))
    except InvalidOperation:
        raise RowError(f'invalid amount: {amount_text}') from None

    if amount == 0:
        raise RowError('amount cannot be zero')
    # numeric(14, 2) caps this at 12 digits before the point. wider would fail
    # the insert and roll back the whole import instead of reporting one bad row
    if abs(amount) >= Decimal('1e12'):
        raise RowError(f'amount out of range: {amount_text}')
    if entry_type == BankTransaction.CREDIT and amount < 0:
        raise RowError('credits must be positive')
    if entry_type == BankTransaction.DEBIT and amount > 0:
        raise RowError('debits must be negative')

    return StatementRow(
        line=line,
        date=value_date,
        description=description,
        amount=amount,
        type=entry_type,
        bank_reference=bank_reference,
    )


def parse_statement(uploaded_file):
    reader, index = read_header(uploaded_file)
    rows, errors = [], []
    for raw in reader:
        # physical line the record finished on, so the header counts as line 1.
        # enumerate would drift on any file with a quoted field spanning lines
        line = reader.line_num
        if not raw:
            continue

        try:
            rows.append(parse_row(raw, index, line))
        except IndexError:
            errors.append({'line': line, 'message': 'row is shorter than the header'})
        except RowError as exc:
            errors.append({'line': line, 'message': str(exc)})

    return rows, errors


def import_statement(uploaded_file, organization):
    rows, errors = parse_statement(uploaded_file)

    # seeded from the database and extended as we go, so a repeat inside one
    # upload counts as a duplicate too
    seen = set(organization.transactions.values_list('bank_reference', flat=True))
    duplicates, fresh = [], []
    for row in rows:
        if row.bank_reference in seen:
            duplicates.append(row)
        else:
            seen.add(row.bank_reference)
            fresh.append(row)

    with transaction.atomic():
        imported = BankTransaction.objects.bulk_create(
            [
                BankTransaction(
                    organization=organization,
                    date=row.date,
                    description=row.description,
                    amount=row.amount,
                    type=row.type,
                    bank_reference=row.bank_reference,
                    status=(
                        BankTransaction.IGNORED
                        if row.type == BankTransaction.DEBIT
                        else BankTransaction.NEEDS_REVIEW
                    ),
                )
                for row in fresh
            ],
            batch_size=500,
        )

        for bank_transaction in imported:
            match_transaction(bank_transaction)

    return {
        'imported': len(fresh),
        'duplicates': len(duplicates),
        'duplicate_lines': [row.line for row in duplicates],
        'errors': errors,
    }


def normalize_reference(value):
    return re.sub(r'[^A-Z0-9]', '', value.upper())


def normalize_name(value):
    words = re.sub(r'[^A-Z0-9]+', ' ', value.upper()).strip().split()
    if words and words[-1] in SUFFIXES:
        words.pop()
    return ' '.join(words)


def normalize_description(value):
    return re.sub(r'[^A-Z0-9]+', ' ', value.upper()).strip()


def name_found(investor_name, description):
    # padded so a fragment inside a longer word can't match
    padded_description = f" {normalize_description(description)} "
    return f" {normalize_name(investor_name)} " in padded_description


def eligible_line_items(bank_transaction):
    # remaining > 0 as a column comparison, since the property can't be queried
    return LineItem.objects.filter(
        organization=bank_transaction.organization,
        amount_funded__lt=F('amount_called'),
        capital_call__call_date__lte=bank_transaction.date,
    ).select_related('investor')


def reference_candidates(bank_transaction, line_items):
    # description collapsed the reference way rather than the name way, so a
    # hyphenated CC-1002 in the text is still findable
    description = normalize_reference(bank_transaction.description)
    bank_reference = normalize_reference(bank_transaction.bank_reference)
    return [
        line_item
        for line_item in line_items
        if normalize_reference(line_item.reference) in description
        or normalize_reference(line_item.reference) in bank_reference
    ]


def name_amount_candidates(bank_transaction, line_items):
    description = normalize_description(bank_transaction.description)
    return [
        line_item
        for line_item in line_items
        if line_item.remaining == bank_transaction.amount
        and name_found(line_item.investor.name, description)
    ]


def propose_match(bank_transaction, line_item, reason):
    return Match.objects.create(
        organization=bank_transaction.organization,
        transaction=bank_transaction,
        line_item=line_item,
        status=Match.PROPOSED,
        reason=reason,
    )


def reference_reason(bank_transaction, line_item):
    if bank_transaction.amount == line_item.remaining:
        detail = (
            f'amount {bank_transaction.amount:,.2f} equals '
            f'remaining {line_item.remaining:,.2f}'
        )
    else:
        detail = (
            f'amount {bank_transaction.amount:,.2f} partially pays '
            f'remaining {line_item.remaining:,.2f}'
        )
    return f'Reference {line_item.reference} found; {detail}'


def name_reason(bank_transaction, line_item):
    return (
        f'Investor {line_item.investor.name} matches {line_item.reference}; '
        f'amount equals remaining {line_item.remaining:,.2f}'
    )


def apply_reference_matches(bank_transaction, line_items):
    if len(line_items) == 1:
        line_item = line_items[0]
        if bank_transaction.amount > line_item.remaining:
            bank_transaction.status = BankTransaction.NEEDS_REVIEW
            bank_transaction.review_reason = (
                f'Amount {bank_transaction.amount:,.2f} exceeds remaining '
                f'{line_item.remaining:,.2f} for {line_item.reference}'
            )
            return

        propose_match(
            bank_transaction, line_item, reference_reason(bank_transaction, line_item)
        )
        bank_transaction.status = BankTransaction.SUGGESTED
        return

    for line_item in line_items:
        propose_match(
            bank_transaction, line_item, reference_reason(bank_transaction, line_item)
        )
    bank_transaction.status = BankTransaction.NEEDS_REVIEW
    bank_transaction.review_reason = (
        f'{len(line_items)} eligible line items share reference '
        f'{line_items[0].reference}'
    )


def apply_name_matches(bank_transaction, line_items):
    if not line_items:
        bank_transaction.status = BankTransaction.NEEDS_REVIEW
        bank_transaction.review_reason = 'No eligible line item matches this payment'
        return

    if len(line_items) == 1:
        line_item = line_items[0]
        propose_match(
            bank_transaction, line_item, name_reason(bank_transaction, line_item)
        )
        bank_transaction.status = BankTransaction.SUGGESTED
        return

    for line_item in line_items:
        propose_match(
            bank_transaction, line_item, name_reason(bank_transaction, line_item)
        )
    bank_transaction.status = BankTransaction.NEEDS_REVIEW
    bank_transaction.review_reason = (
        f'{len(line_items)} eligible line items match investor name and amount'
    )


def match_transaction(bank_transaction):
    if bank_transaction.type == BankTransaction.DEBIT:
        return

    line_items = list(eligible_line_items(bank_transaction))
    reference_hits = reference_candidates(bank_transaction, line_items)

    # a reference hit ends it, the name rule only runs when none was found
    if reference_hits:
        apply_reference_matches(bank_transaction, reference_hits)
    else:
        apply_name_matches(
            bank_transaction, name_amount_candidates(bank_transaction, line_items)
        )

    bank_transaction.save()


def approve_match(match_id, organization):
    with transaction.atomic():
        # match row first, then line item, always in that order, so two
        # approvals for different matches on one line item queue up rather
        # than deadlock
        match = (
            Match.objects.select_for_update()
            .filter(id=match_id, organization=organization)
            .first()
        )
        if match is None:
            raise exceptions.NotFound('unknown match')

        line_item = LineItem.objects.select_for_update().get(id=match.line_item_id)

        if match.status != Match.PROPOSED:
            raise Conflict(f'Match {match.id} is already {match.status}')

        bank_transaction = match.transaction
        if bank_transaction.status == BankTransaction.RECONCILED:
            raise Conflict('transaction is already reconciled')
        if bank_transaction.amount > line_item.remaining:
            raise Conflict(
                f'Amount {bank_transaction.amount:,.2f} exceeds remaining '
                f'{line_item.remaining:,.2f} for {line_item.reference}'
            )

        line_item.amount_funded += bank_transaction.amount
        line_item.refresh_status()
        line_item.save()

        match.status = Match.APPROVED
        match.save()

        # this transaction's other matches only, not matches from other
        # transactions pointing at the same line item
        bank_transaction.matches.exclude(id=match.id).update(status=Match.REJECTED)

        bank_transaction.status = BankTransaction.RECONCILED
        bank_transaction.save()

    return match, line_item, bank_transaction


def reject_match(match_id, organization):
    with transaction.atomic():
        match = (
            Match.objects.select_for_update()
            .filter(id=match_id, organization=organization)
            .first()
        )
        if match is None:
            raise exceptions.NotFound('unknown match')
        if match.status == Match.APPROVED:
            raise Conflict('an approved match cannot be rejected')

        match.status = Match.REJECTED
        match.save()

        bank_transaction = match.transaction
        if not bank_transaction.matches.filter(status=Match.PROPOSED).exists():
            bank_transaction.status = BankTransaction.NEEDS_REVIEW
            bank_transaction.review_reason = 'All suggested matches were rejected'
            bank_transaction.save()

    return match, bank_transaction


def ignore_transaction(transaction_id, organization):
    with transaction.atomic():
        bank_transaction = (
            BankTransaction.objects.select_for_update()
            .filter(id=transaction_id, organization=organization)
            .first()
        )
        if bank_transaction is None:
            raise exceptions.NotFound('unknown transaction')
        if bank_transaction.status == BankTransaction.RECONCILED:
            raise Conflict('a reconciled transaction cannot be ignored')
        if bank_transaction.status == BankTransaction.IGNORED:
            raise Conflict('transaction is already ignored')

        bank_transaction.matches.filter(status=Match.PROPOSED).update(
            status=Match.REJECTED
        )
        bank_transaction.status = BankTransaction.IGNORED
        bank_transaction.save()

    return bank_transaction
