from rest_framework import exceptions


class Conflict(exceptions.APIException):
    status_code = 409
