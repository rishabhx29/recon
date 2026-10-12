from rest_framework import serializers

from .models import BankTransaction, CapitalCall, LineItem, Match, Organization


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ['slug', 'name']


class CapitalCallSerializer(serializers.ModelSerializer):
    class Meta:
        model = CapitalCall
        fields = ['id', 'call_date', 'due_date']


class LineItemSummarySerializer(serializers.ModelSerializer):
    investor = serializers.CharField(source='investor.name')
    # declared rather than left to introspection, otherwise remaining goes out
    # as a json float instead of a decimal string
    remaining = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True
    )

    class Meta:
        model = LineItem
        fields = ['id', 'reference', 'investor', 'remaining']


class LineItemSerializer(serializers.ModelSerializer):
    investor = serializers.CharField(source='investor.name')
    remaining = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True
    )
    capital_call = CapitalCallSerializer(read_only=True)

    class Meta:
        model = LineItem
        fields = [
            'id',
            'reference',
            'investor',
            'capital_call',
            'amount_called',
            'amount_funded',
            'remaining',
            'status',
        ]


class MatchSerializer(serializers.ModelSerializer):
    line_item = LineItemSummarySerializer(read_only=True)

    class Meta:
        model = Match
        fields = ['id', 'status', 'reason', 'line_item']


class BankTransactionSerializer(serializers.ModelSerializer):
    matches = MatchSerializer(many=True, read_only=True)

    class Meta:
        model = BankTransaction
        fields = [
            'id',
            'date',
            'description',
            'amount',
            'type',
            'bank_reference',
            'status',
            'review_reason',
            'matches',
        ]
