from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand

from reconciliation.models import (
    CapitalCall,
    InvestorEntity,
    LineItem,
    Organization,
)

SEED = [
    {
        'slug': 'northwind',
        'name': 'Northwind Ventures',
        'calls': [
            {
                'call_date': date(2026, 3, 25),
                'due_date': date(2026, 4, 10),
                'line_items': [
                    ('Haller Capital LLC', 'CC-1001', '27500.00'),
                    ('Rahul Shah Trust', 'CC-1002', '25000.00'),
                    ('Patel Family Trust', 'CC-1003', '12500.00'),
                    ('Meridian Partners LP', 'CC-1004', '15000.00'),
                    ('Oakridge Holdings LLC', 'CC-1005', '15000.00'),
                ],
            },
            {
                'call_date': date(2026, 4, 1),
                'due_date': date(2026, 4, 20),
                'line_items': [
                    ('Oakridge Holdings LLC', 'CC-1006', '15000.00'),
                ],
            },
        ],
    },
    {
        'slug': 'bluebird',
        'name': 'Bluebird Capital',
        'calls': [
            {
                'call_date': date(2026, 4, 1),
                'due_date': date(2026, 4, 15),
                'line_items': [
                    ('Cedar Grove Fund LP', 'CC-2001', '40000.00'),
                ],
            },
        ],
    },
]


class Command(BaseCommand):
    help = 'create the two demo organizations with their capital calls'

    def handle(self, *args, **options):
        for organization_spec in SEED:
            organization, _ = Organization.objects.get_or_create(
                slug=organization_spec['slug'],
                defaults={'name': organization_spec['name']},
            )
            for call_spec in organization_spec['calls']:
                capital_call, _ = CapitalCall.objects.get_or_create(
                    organization=organization,
                    call_date=call_spec['call_date'],
                    due_date=call_spec['due_date'],
                )
                for investor_name, reference, amount in call_spec['line_items']:
                    investor, _ = InvestorEntity.objects.get_or_create(
                        organization=organization, name=investor_name
                    )
                    LineItem.objects.get_or_create(
                        organization=organization,
                        reference=reference,
                        defaults={
                            'capital_call': capital_call,
                            'investor': investor,
                            'amount_called': Decimal(amount),
                        },
                    )

        self.stdout.write(
            f'{Organization.objects.count()} organizations, '
            f'{CapitalCall.objects.count()} capital calls, '
            f'{InvestorEntity.objects.count()} investors, '
            f'{LineItem.objects.count()} line items'
        )
