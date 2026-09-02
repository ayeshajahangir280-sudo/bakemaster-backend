from django.db.models.deletion import ProtectedError, RestrictedError
from rest_framework.response import Response
from rest_framework.views import exception_handler

def api_exception_handler(exc,context):
    if isinstance(exc, (ProtectedError, RestrictedError)):
        return Response(
            {
                "success": False,
                "message": "This record is still in use and cannot be deleted. Remove or update the related records first.",
                "errors": {"detail": str(exc)},
            },
            status=409,
        )
    response=exception_handler(exc,context)
    if response is not None:
        detail=response.data
        message=detail.get("detail","Request failed.") if isinstance(detail,dict) else "Request failed."
        response.data={"success":False,"message":str(message),"errors":detail}
    return response
