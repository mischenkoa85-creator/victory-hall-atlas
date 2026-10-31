"""Fixed-scope native service entrypoint. No automatic work on import."""
import json,os,signal,threading
import psycopg
from notification_runtime import make_worker
from notification_worker import WorkerUnavailable

SOCKET='/var/run/postgresql-victory-hall-green'
PORT=55435
DATABASE='victory_hall_green_dev'
PRINCIPAL='vh_atlas_notification_login'
EXPECTED_OS_USER='vh-atlas-notify'

def native_connect():
    # Peer authentication only. No password, pgpass, authn session or alternate
    # database fallback is supported. The unit clears libpq environment options.
    connection=psycopg.connect(host=SOCKET,port=PORT,dbname=DATABASE,user=PRINCIPAL,
        connect_timeout=5,passfile='/dev/null',sslmode='disable',application_name='atlas-notification-worker')
    try:
        row=connection.execute("SELECT current_database(),session_user,inet_server_addr(),current_setting('port')").fetchone()
        if row!=(DATABASE,PRINCIPAL,None,str(PORT)):raise WorkerUnavailable()
        connection.commit();return connection
    except Exception:
        connection.close();raise WorkerUnavailable() from None

def emit(value):print(json.dumps(value,separators=(',',':')),flush=True)

def run_loop(worker,stop,*,output=emit,interval=2):
    if not 1<=interval<=60:raise WorkerUnavailable()
    last_failure=None;ready=False
    output({'component':'atlas_notifications','state':'configured'})
    while not stop.is_set():
        try:results=worker.tick(max_jobs=1)
        except Exception:results=[{'state':'worker_unavailable'}]
        failure=False
        for value in results:
            # A strict projection prevents future repository errors from being
            # copied into service logs. UUID and enums are worker-owned values.
            state=value.get('state');allowed={'database_unavailable_before_send','dispatch_outcome_unknown_no_send','scope_cancelled','accepted','rejected','retryable','expired_endpoint','uncertain','finish_outcome_unknown_no_resend','worker_unavailable'}
            if state not in allowed:state='worker_unavailable'
            if state in ('database_unavailable_before_send','worker_unavailable'):
                failure=True
                if state==last_failure:continue
                last_failure=state
            else:last_failure=None
            record={'component':'atlas_notifications','state':state}
            if 'job_id' in value:
                try:
                    from uuid import UUID
                    record['job_id']=str(UUID(str(value['job_id'])))
                except (ValueError,TypeError,AttributeError):pass
            status=value.get('http_status')
            if type(status) is int and 100<=status<=599:record['http_status']=status
            output(record)
        if not failure and not ready:
            output({'component':'atlas_notifications','state':'ready'});ready=True
        if failure:ready=False
        stop.wait(30 if failure else interval)
    output({'component':'atlas_notifications','state':'stopped'})

def main():
    try:
        if os.name!='posix':raise WorkerUnavailable()
        import pwd
        if pwd.getpwuid(os.geteuid()).pw_name!=EXPECTED_OS_USER:raise WorkerUnavailable()
        # Do not read or retain their values. Fixed native peer config is the
        # sole source of connection parameters.
        for name in tuple(os.environ):
            if name.startswith('PG'):os.environ.pop(name,None)
        stop=threading.Event()
        for signum in (signal.SIGTERM,signal.SIGINT):signal.signal(signum,lambda *_:stop.set())
        worker=make_worker(native_connect);run_loop(worker,stop)
    except Exception:
        emit({'component':'atlas_notifications','state':'startup_unavailable'});return 1
    return 0

if __name__=='__main__':raise SystemExit(main())
