from django.core.management.base import BaseCommand

from reconciliation.models import Organization


class Command(BaseCommand):
    help = 'create the two demo organizations'

    def handle(self, *args, **options):
        Organization.objects.get_or_create(
            slug='northwind', defaults={'name': 'Northwind Ventures'}
        )
        Organization.objects.get_or_create(
            slug='bluebird', defaults={'name': 'Bluebird Capital'}
        )
        self.stdout.write(
            f'{Organization.objects.count()} organizations'
        )
