import csv
import io
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.db import transaction

from .models import BankTransaction

REQUIRED_COLUMNS = ['date', 'description', 'amount', 'type', 'reference']


class MissingColumns(Exception):
    # the file is unusable and nothing gets saved. deliberately different from
    # a bad row, which gets skipped and reported
    pass


class RowError(Exception):
    pass


def read_header(uploaded_file):
    # utf-8-sig eats the byte order mark Excel adds when it saves a csv,
    # which would otherwise leave a stray "﻿" in front of the first
    # column name
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
        # line_num counts physical lines in the file, so the header is line 1.
        # enumerate would count rows instead and drift as soon as a quoted
        # description wraps onto a second line
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

    # one set covering references already stored and ones seen earlier in this
    # same upload, which is how a repeat inside a single file gets caught
    seen = set(organization.transactions.values_list('bank_reference', flat=True))
    duplicates, fresh = [], []
    for row in rows:
        if row.bank_reference in seen:
            duplicates.append(row)
        else:
            seen.add(row.bank_reference)
            fresh.append(row)

    with transaction.atomic():
        BankTransaction.objects.bulk_create(
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

    return {
        'imported': len(fresh),
        'duplicates': len(duplicates),
        'duplicate_lines': [row.line for row in duplicates],
        'errors': errors,
    }
