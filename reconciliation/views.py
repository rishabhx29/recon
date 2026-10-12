from rest_framework import exceptions
from rest_framework.decorators import api_view
from rest_framework.response import Response

from . import services
from .models import Organization


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

    return Response(summary)
