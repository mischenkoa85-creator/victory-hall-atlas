"""Build a NEW local code-only candidate from the exact 5295450 BFF snapshot.

Does not import/run protected runtime, copy secrets, provision services or deploy.
Output directory must not exist. Existing source snapshot is never modified.
"""
import argparse,ast,hashlib,json,difflib
from pathlib import Path

BASE_MANIFEST='5295450a2d458ca6a3b6ff6a3977e55d61047bc9af2a3c0d65c1c36a743142f6'
PIN_ASSEMBLY='65cf39c0c961100ad547111110cbbac5aa7926598576790989fb3b62e2abc134'
PIN_APP='414601426e04295795ca957a013046ce0b0728de597615ad78e068789ff61829'
RUNTIME_MODULES=('warehouse_api.py','board_api.py','attachment_store.py','attachment_api.py','workspace_api.py','command_resolution_api.py')
def sha(b):return hashlib.sha256(b).hexdigest()
def replace_once(text,before,after):
    if text.count(before)!=1:raise ValueError('PATCH_CONTEXT_COUNT')
    return text.replace(before,after,1)
def build(source,operations,output):
    if output.exists():raise ValueError('OUTPUT_MUST_BE_NEW')
    raw=(source/'SOURCE_MANIFEST.json').read_bytes()
    if sha(raw)!=BASE_MANIFEST:raise ValueError('BFF_MANIFEST_DRIFT')
    manifest=json.loads(raw)
    # Copy only source-code/static artifacts from the accepted manifest. The
    # protected runtime loader is code, but its live provisioning is excluded.
    originals={}
    for name,h in manifest['files'].items():
        if name.startswith('session/runtime-config-candidate/'):
            continue
        rel=Path(name)
        if rel.is_absolute() or '..' in rel.parts:raise ValueError('SOURCE_PATH')
        b=(source/rel).read_bytes()
        if sha(b)!=h:raise ValueError('BFF_SOURCE_DRIFT:'+name)
        originals[name]=b
    a=originals['session/service-candidate/assembly.py'];app=originals['session/bff/app.py']
    if sha(a)!=PIN_ASSEMBLY or sha(app)!=PIN_APP:raise ValueError('BASELINE_PIN')
    at=a.decode();pt=app.decode()
    at=replace_once(at,'def build_application(runtime: RuntimeInputs, *, public_fetch=None, token_transport=None):',
        'def build_application(runtime: RuntimeInputs, *, public_fetch=None, token_transport=None, operations_store=None):')
    at=replace_once(at,'        attach(app, repository)\n',
        '        attach(app, repository)\n        from atlas_operations_integration import attach_operations\n        attach_operations(app, repository, store=operations_store)\n')
    pt=replace_once(pt,'        raw=request.headers.get(\'content-length\',\'0\')\n        if not raw.isdigit() or int(raw)>32768:',
        "        from atlas_operations_integration import request_body_limit\n        raw=request.headers.get('content-length','0')\n        if not raw.isdigit() or int(raw)>request_body_limit(request):")
    ast.parse(at);ast.parse(pt)
    changed={'session/service-candidate/assembly.py':at.encode(),'session/bff/app.py':pt.encode()}
    files={**originals,**changed}
    files['session/service-candidate/atlas_operations_integration.py']=(operations/'integration/atlas_operations_integration.py').read_bytes()
    for name in RUNTIME_MODULES:files['operations/'+name]=(operations/name).read_bytes()
    output.mkdir(parents=True)
    for name,b in files.items():
        if name.endswith('.py'):ast.parse(b.decode())
        target=output/'release'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(b)
    patches={}
    for name,b in changed.items():
        patch=''.join(difflib.unified_diff(originals[name].decode().splitlines(True),b.decode().splitlines(True),fromfile='baseline/'+name,tofile='candidate/'+name))
        patches[name]=patch
    (output/'code-delta.patch').write_text('\n'.join(patches.values()),encoding='utf8')
    result={'status':'LOCAL_CODE_CANDIDATE_NOT_DEPLOYED','baseline_manifest_sha256':BASE_MANIFEST,
     'changed_existing_files':list(changed),'new_files':sorted(set(files)-set(originals)),
     'files':{n:{'sha256':sha(b),'bytes':len(b)} for n,b in files.items()},
     'private_photo_root':'/var/lib/victory-hall-atlas-attachments','required_systemd_write_path':'/var/lib/victory-hall-atlas-attachments',
     'required_sql':'reviewed operations SQL001-005 must already be migrated before wiring',
     'protected_runtime_read_or_copied':False,'deployment':False}
    (output/'INTEGRATION_MANIFEST.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    return result
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--operations',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();result=build(args.source,args.operations,args.output);print(json.dumps({'status':result['status'],'files':len(result['files']),'changed':result['changed_existing_files']}))
