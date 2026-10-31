"""Facility-scoped, read-only access to the sanitized Deye projection."""
from uuid import UUID
from fastapi import Request
from fastapi.responses import JSONResponse
from bff.models import AuthenticationDenied, PermissionDenied, ServiceUnavailable
from bff.security import authenticated_secret
from atlas_power_projection import ProjectionUnavailable, read_projection

FACILITY_ID = UUID('7faea0c2-6f17-8c3c-88b5-77858aa65072')


def attach_power(app, repository):
    @app.get('/v1/session/power/{facility_id}')
    def power(facility_id: UUID, request: Request):
        try:
            # The existing session context verifies the cookie and current SQL
            # scope before touching the private projection. A URL grants nothing.
            with repository._request(authenticated_secret(request)) as connection:
                if facility_id != FACILITY_ID:
                    raise PermissionDenied()
                row = connection.execute('SELECT atlas_ops.workspace_context(%s) AS result',
                                         (facility_id,)).fetchone()
                context = row.get('result') if isinstance(row, dict) else None
                if not isinstance(context, dict) or context.get('facility_id') != str(FACILITY_ID):
                    raise ServiceUnavailable()
            result = read_projection()
            return JSONResponse(result, headers={'Cache-Control': 'no-store'})
        except AuthenticationDenied:
            return JSONResponse({'code': 'AUTHENTICATION_REQUIRED'}, status_code=401, headers={'Cache-Control': 'no-store'})
        except PermissionDenied:
            return JSONResponse({'code': 'SCOPE_DENIED'}, status_code=403, headers={'Cache-Control': 'no-store'})
        except (ProjectionUnavailable, ServiceUnavailable):
            return JSONResponse({'code': 'POWER_UNAVAILABLE'}, status_code=503, headers={'Cache-Control': 'no-store'})
