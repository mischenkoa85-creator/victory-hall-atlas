"""Candidate assembly hook, copied beside service-candidate/assembly.py.

No environment or credential reads. Production uses a fixed private filesystem
directory. Optional store injection is a trusted factory/testing parameter only.
"""
from pathlib import Path
from collections import deque
import importlib,re,sys
from starlette.requests import Request
from starlette.responses import JSONResponse

SESSION=Path(__file__).resolve().parent.parent
OPERATIONS=SESSION.parent/'operations'
PHOTO_ROOT=Path('/var/lib/victory-hall-atlas-attachments')
JSON_BODY_LIMIT=32768
PHOTO_BODY_LIMIT=5*1024*1024
_UUID=r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'
_UPLOAD=re.compile(r'/v1/session/attachments/'+_UUID+r'/tasks/'+_UUID)
_MEDIA={'image/jpeg','image/png','image/webp'}
_PREFIXES=('/v1/session/warehouse/','/v1/session/board/','/v1/session/attachments/','/v1/session/operations/')

def _route_path(scope):
    path=scope.get('path','')
    return path[len('/block8-reporting'):] if path.startswith('/block8-reporting/') else path

def request_body_limit(request):
    """Only an exact raw-image upload route gets the 5 MiB header allowance."""
    path=_route_path(request.scope)
    media=request.headers.get('content-type','').split(';',1)[0].strip().lower()
    encoding=request.headers.get('content-encoding','identity').strip().lower()
    if request.method=='POST' and _UPLOAD.fullmatch(path) and media in _MEDIA and encoding=='identity':
        return PHOTO_BODY_LIMIT
    return JSON_BODY_LIMIT

class OperationsBodyLimit:
    """Bound real bytes before FastAPI parses new operations POST bodies.

    Older auth/report routes are untouched. Valid data are replayed as the same
    bounded byte chunks, without JSON parsing, transformation or credential reads.
    """
    def __init__(self,app):self.app=app
    async def __call__(self,scope,receive,send):
        if scope.get('type')!='http' or scope.get('method')!='POST' or not any(_route_path(scope).startswith(p) for p in _PREFIXES):
            await self.app(scope,receive,send);return
        request=Request(scope);limit=request_body_limit(request)
        async def reject(code=413):
            response=JSONResponse({'error':'REQUEST_TOO_LARGE' if code==413 else 'INVALID_REQUEST'},status_code=code,
            headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer','X-Content-Type-Options':'nosniff',
                     'X-Frame-Options':'DENY','Content-Security-Policy':"default-src 'none'; frame-ancestors 'none'"})
            await response(scope,receive,send)
        length=request.headers.get('content-length')
        if length is not None and (not length.isascii() or not length.isdigit() or len(length)>12 or int(length)>limit):
            await reject();return
        chunks=deque();total=0
        while True:
            event=await receive()
            if event['type']=='http.disconnect':return
            if event['type']!='http.request':await reject(400);return
            chunk=event.get('body',b'');total+=len(chunk)
            if total>limit:await reject();return
            if chunk:chunks.append(chunk)
            if not event.get('more_body',False):break
        body_sent=False
        async def replay():
            nonlocal body_sent
            if chunks:
                chunk=chunks.popleft();body_sent=not chunks
                return {'type':'http.request','body':chunk,'more_body':bool(chunks)}
            if not body_sent:
                body_sent=True;return {'type':'http.request','body':b'','more_body':False}
            return await receive()
        await self.app(scope,replay,send)

def _module(name):
    module=importlib.import_module(name)
    if Path(module.__file__).resolve()!=OPERATIONS/(name+'.py'):
        raise RuntimeError('OPERATIONS_MODULE_PATH_MISMATCH')
    return module

def attach_operations(app,repository,*,store=None):
    if getattr(app.state,'atlas_operations_attached',False) or app.middleware_stack is not None:
        raise RuntimeError('OPERATIONS_FACTORY_ONLY')
    for route in app.routes:
        if any(getattr(route,'path','').startswith(prefix) for prefix in _PREFIXES):
            raise RuntimeError('OPERATIONS_ROUTE_COLLISION')
    for name in ('models','security','repository'):
        module=importlib.import_module('bff.'+name)
        if Path(module.__file__).resolve()!=SESSION/'bff'/(name+'.py'):
            raise RuntimeError('OPERATIONS_BFF_BINDING_MISMATCH')
    if not OPERATIONS.is_dir() or OPERATIONS.resolve()!=OPERATIONS:
        raise RuntimeError('OPERATIONS_DIRECTORY_MISSING_OR_REDIRECTED')
    sys.path.insert(0,str(OPERATIONS))
    storage=_module('attachment_store')
    if storage.MAX_BYTES!=PHOTO_BODY_LIMIT:
        raise RuntimeError('OPERATIONS_IMAGE_LIMIT_MISMATCH')
    if store is None:
        storage._pillow()  # Missing/relaxed decoder fails at startup, before any route is served.
        store=storage.PrivateAttachmentStore(PHOTO_ROOT)
    if not callable(getattr(store,'put_image',None)) or not callable(getattr(store,'read_blob',None)):
        raise RuntimeError('OPERATIONS_STORE_REQUIRED')
    _module('warehouse_api').attach_warehouse(app,repository)
    _module('board_api').attach_board(app,repository,attachment_verifier=storage.ActualAttachmentVerifier(store))
    _module('attachment_api').attach_attachments(app,repository,store)
    _module('workspace_api').attach_workspace(app,repository)
    _module('command_resolution_api').attach_command_resolution(app,repository)
    app.add_middleware(OperationsBodyLimit)
    app.state.atlas_operations_attached=True
