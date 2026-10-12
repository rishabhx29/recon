from rest_framework import exceptions
from rest_framework.decorators import api_view
from rest_framework.response import Response

from . import services
from .models import BankTransaction, LineItem, Match, Organization
from .serializers import (
    BankTransactionSerializer,
    LineItemSerializer,
    MatchSerializer,
    OrganizationSerializer,
)


def organization_from(request):
    slug = request.headers.get('X-Organization')
    if not slug:
        raise exceptions.ParseError('X-Organization header is required')
    try:
        return Organization.objects.get(slug=slug)
    except Organization.DoesNotExist:
        raise exceptions.NotFound('unknown organization')


@api_view(['GET'])
def health(request):
    return Response({'ok': True})


@api_view(['POST'])
def import_statement_view(request):
    organization = organization_from(request)
    upload = request.FILES.get('file')
    if upload is None:
        raise exceptions.ParseError('no file uploaded')

    try:
        summary = services.import_statement(upload, organization)
    except services.MissingColumns as exc:
        raise exceptions.ParseError(str(exc)) from exc
    except UnicodeDecodeError:
        raise exceptions.ParseError('file is not valid utf-8') from None

    return Response(summary)


# no header needed here, the switcher has to load before one is chosen
@api_view(['GET'])
def organizations(request):
    queryset = Organization.objects.order_by('slug')
    return Response(OrganizationSerializer(queryset, many=True).data)


@api_view(['GET'])
def transactions(request):
    organization = organization_from(request)
    queryset = (
        BankTransaction.objects.filter(organization=organization)
        .prefetch_related('matches__line_item__investor')
    )
    status = request.query_params.get('status')
    if status:
        queryset = queryset.filter(status=status)

    return Response({'results': BankTransactionSerializer(queryset, many=True).data})


@api_view(['GET'])
def line_items(request):
    organization = organization_from(request)
    queryset = LineItem.objects.filter(organization=organization).select_related(
        'investor', 'capital_call'
    )
    return Response({'results': LineItemSerializer(queryset, many=True).data})


def match_or_404(match_id, organization):
    # scoped before anything else runs, so an id from another organization is
    # indistinguishable from one that does not exist
    if not Match.objects.filter(id=match_id, organization=organization).exists():
        raise exceptions.NotFound('unknown match')


def transaction_or_404(transaction_id, organization):
    if not BankTransaction.objects.filter(
        id=transaction_id, organization=organization
    ).exists():
        raise exceptions.NotFound('unknown transaction')


@api_view(['POST'])
def approve_match_view(request, match_id):
    organization = organization_from(request)
    match_or_404(match_id, organization)

    match, line_item, bank_transaction = services.approve_match(match_id, organization)

    return Response(
        {
            'match': MatchSerializer(match).data,
            'line_item': LineItemSerializer(line_item).data,
            'transaction': BankTransactionSerializer(bank_transaction).data,
        }
    )


@api_view(['POST'])
def reject_match_view(request, match_id):
    organization = organization_from(request)
    match_or_404(match_id, organization)

    match, bank_transaction = services.reject_match(match_id, organization)

    return Response(
        {
            'match': MatchSerializer(match).data,
            'transaction': BankTransactionSerializer(bank_transaction).data,
        }
    )


@api_view(['POST'])
def ignore_transaction_view(request, transaction_id):
    organization = organization_from(request)
    transaction_or_404(transaction_id, organization)

    bank_transaction = services.ignore_transaction(transaction_id, organization)
    return Response({'transaction': BankTransactionSerializer(bank_transaction).data})
