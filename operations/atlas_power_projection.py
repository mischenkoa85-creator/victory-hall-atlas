"""Minimal Atlas projection of LiveState.snapshot; no telemetry or credentials.

The same reviewed module is installed beside the ingester and in BFF operations.
Production paths and Linux identities are fixed; only the ingester writes.
"""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import math
import os
import re
import stat
import struct
import sys
import uuid

FRESHNESS_S = 15
OFFLINE_S = 30
MAX_BYTES = 4096
FILE_NAME = 'atlas-power.json'
DIRECTORY = '/run/deye-ingest'
PRODUCER_UID = 983
PRODUCER_GID = 975
READER_UID = 986
FIELDS = frozenset(('source', 'grid', 'pv', 'pv_power_kw', 'last_observed_at',
                    'last_received_at', 'age_s', 'freshness_s',
                    'grid_absent_since', 'grid_time_quality'))
_TIME = re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})\Z')
_POWER = re.compile(r'\d{1,12}(?:\.\d{1,12})?(?:[eE][+-]?\d{1,3})?\Z')
_UNDEFINED = 0xffffffff
FILE_ACL = struct.pack('<I', 2) + b''.join(struct.pack('<HHI', *entry) for entry in (
    (1, 6, _UNDEFINED), (2, 4, READER_UID), (4, 0, _UNDEFINED),
    (16, 4, _UNDEFINED), (32, 0, _UNDEFINED)))


class ProjectionUnavailable(Exception):
    """Deliberately contains no path, file contents or operating-system detail."""


def _instant(value):
    if not isinstance(value, str) or not _TIME.fullmatch(value):
        return None
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(timezone.utc)
    except (ValueError, OverflowError):
        return None


def _now(value):
    value = datetime.now(timezone.utc) if value is None else value
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ProjectionUnavailable()
    return value.astimezone(timezone.utc)


def _power(value):
    if not isinstance(value, str) or not _POWER.fullmatch(value):
        return None
    try:
        number = Decimal(value)
        # Bounded engineering value, not a source of JSON NaN/Infinity or huge text.
        if not number.is_finite() or not 0 <= number <= Decimal('1000000000'):
            return None
        return format(number.normalize(), 'f')
    except InvalidOperation:
        return None


def project_snapshot(snapshot, now=None):
    """Pure allowlist transform. Invalid/missing/future dates never become fresh."""
    now = _now(now)
    if not isinstance(snapshot, dict):
        raise ProjectionUnavailable()
    observed = _instant(snapshot.get('last_observed_at'))
    received = _instant(snapshot.get('last_received_at'))
    observed = observed if observed is not None and observed <= now else None
    received = received if received is not None and received <= now else None
    observed_age = (now - observed).total_seconds() if observed is not None else None
    received_age = (now - received).total_seconds() if received is not None else None
    source = snapshot.get('source')
    if source not in ('FRESH', 'STALE', 'OFFLINE') or received_age is None or received_age >= OFFLINE_S:
        source = 'OFFLINE'
    elif source == 'FRESH' and (observed_age is None or observed_age >= FRESHNESS_S or received_age >= FRESHNESS_S):
        source = 'STALE'
    fresh = source == 'FRESH'
    grid = snapshot.get('grid') if fresh and snapshot.get('grid') in ('PRESENT', 'ABSENT') else 'UNKNOWN'
    pv = snapshot.get('pv') if fresh and snapshot.get('pv') in ('GENERATING', 'ZERO') else 'UNKNOWN'
    # LiveState only supplies this number while its own PV sample is fresh.
    # UNKNOWN may mean the model's generation threshold is not configured;
    # preserve observed power without inventing GENERATING/ZERO classification.
    power = _power(snapshot.get('pv_power_kw')) if fresh else None
    quality = snapshot.get('grid_time_quality') if grid != 'UNKNOWN' else 'UNKNOWN'
    quality = quality if quality in ('CONFIRMED', 'UNCERTAIN') else 'UNKNOWN'
    absent = _instant(snapshot.get('grid_absent_since'))
    absent = absent if (grid == 'ABSENT' and quality == 'CONFIRMED' and absent is not None
                        and observed is not None and absent <= observed) else None
    return {
        'source': source, 'grid': grid, 'pv': pv, 'pv_power_kw': power,
        'last_observed_at': observed.isoformat() if observed is not None else None,
        'last_received_at': received.isoformat() if received is not None else None,
        'age_s': max(observed_age, received_age) if observed_age is not None and received_age is not None else None,
        'freshness_s': FRESHNESS_S,
        'grid_absent_since': absent.isoformat() if absent is not None else None,
        'grid_time_quality': quality,
    }


def _unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ProjectionUnavailable()
        value[key] = item
    return value


def decode_projection(raw, now=None):
    """Strict file contract, followed by request-time freshness revalidation."""
    try:
        if not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_BYTES:
            raise ProjectionUnavailable()
        data = json.loads(raw, object_pairs_hook=_unique, parse_constant=lambda _: (_ for _ in ()).throw(ProjectionUnavailable()))
        if not isinstance(data, dict) or set(data) != FIELDS:
            raise ProjectionUnavailable()
        for field, allowed in (('source', ('FRESH', 'STALE', 'OFFLINE')),
                               ('grid', ('PRESENT', 'ABSENT', 'UNKNOWN')),
                               ('pv', ('GENERATING', 'ZERO', 'UNKNOWN')),
                               ('grid_time_quality', ('CONFIRMED', 'UNCERTAIN', 'UNKNOWN'))):
            if not isinstance(data[field], str) or data[field] not in allowed:
                raise ProjectionUnavailable()
        if type(data['freshness_s']) is not int or data['freshness_s'] != FRESHNESS_S:
            raise ProjectionUnavailable()
        if data['age_s'] is not None and (type(data['age_s']) not in (int, float)
                                        or not math.isfinite(data['age_s']) or data['age_s'] < 0):
            raise ProjectionUnavailable()
        for field in ('last_observed_at', 'last_received_at', 'grid_absent_since'):
            if data[field] is not None and _instant(data[field]) is None:
                raise ProjectionUnavailable()
        if data['pv_power_kw'] is not None and _power(data['pv_power_kw']) is None:
            raise ProjectionUnavailable()
        return project_snapshot(data, now)
    except (ValueError, TypeError, OverflowError, UnicodeError, RecursionError):
        raise ProjectionUnavailable() from None


def _check_file(info, acl, *, allow_empty=False):
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != PRODUCER_UID or info.st_gid != PRODUCER_GID
            or stat.S_IMODE(info.st_mode) != 0o640 or info.st_nlink != 1 or acl != FILE_ACL
            or not (0 if allow_empty else 1) <= info.st_size <= MAX_BYTES):
        raise ProjectionUnavailable()


def _open_directory(*, writer=False):
    """O_PATH on reader directories needs traversal only, never directory read."""
    if sys.platform != 'linux':
        raise ProjectionUnavailable()
    flags = os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open('/', flags)
    try:
        for part in ('run', 'deye-ingest'):
            info = os.fstat(fd)
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
                raise ProjectionUnavailable()
            next_fd = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        info = os.fstat(fd)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != PRODUCER_UID
                or info.st_gid != PRODUCER_GID or info.st_mode & 0o067):
            raise ProjectionUnavailable()
        if writer:
            next_fd = os.open('.', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
            if (os.fstat(next_fd).st_dev, os.fstat(next_fd).st_ino) != (info.st_dev, info.st_ino):
                os.close(next_fd)
                raise ProjectionUnavailable()
            os.close(fd)
            fd = next_fd
        return fd
    except BaseException:
        os.close(fd)
        raise


def _file_acl(fd):
    return os.getxattr(fd, 'system.posix_acl_access')


def _read_fd(fd):
    before = os.fstat(fd)
    _check_file(before, _file_acl(fd))
    data = bytearray()
    while len(data) <= MAX_BYTES:
        block = os.read(fd, MAX_BYTES + 1 - len(data))
        if not block:
            break
        data.extend(block)
    after = os.fstat(fd)
    _check_file(after, _file_acl(fd))
    shape = lambda i: (i.st_dev, i.st_ino, i.st_size, i.st_mtime_ns, i.st_ctime_ns)
    if shape(before) != shape(after) or len(data) != before.st_size or len(data) > MAX_BYTES:
        raise ProjectionUnavailable()
    return bytes(data)


def read_projection(now=None):
    directory = fd = None
    try:
        directory = _open_directory()
        fd = os.open(FILE_NAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=directory)
        return decode_projection(_read_fd(fd), now)
    except (OSError, ValueError, TypeError, AttributeError):
        raise ProjectionUnavailable() from None
    finally:
        if fd is not None:
            os.close(fd)
        if directory is not None:
            os.close(directory)


def export_snapshot(snapshot, now=None):
    """Owner-only atomic replace, with the exact reader ACL on the temporary fd."""
    data = (json.dumps(project_snapshot(snapshot, now), ensure_ascii=True, allow_nan=False,
                       sort_keys=True, separators=(',', ':')) + '\n').encode('ascii')
    directory = fd = None
    temporary = None
    try:
        if sys.platform != 'linux' or os.geteuid() != PRODUCER_UID or os.getegid() != PRODUCER_GID:
            raise ProjectionUnavailable()
        directory = _open_directory(writer=True)
        # Never replace a link, foreign inode, permissive file, or other object.
        try:
            old = os.open(FILE_NAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=directory)
        except FileNotFoundError:
            pass
        else:
            try:
                _check_file(os.fstat(old), _file_acl(old))
            finally:
                os.close(old)
        temporary = '.atlas-power-' + uuid.uuid4().hex + '.tmp'
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=directory)
        # Setting the complete ACL removes inherited grants; group:: and other:: are zero.
        os.setxattr(fd, 'system.posix_acl_access', FILE_ACL)
        _check_file(os.fstat(fd), _file_acl(fd), allow_empty=True)
        pending = memoryview(data)
        while pending:
            written = os.write(fd, pending)
            if written <= 0:
                raise ProjectionUnavailable()
            pending = pending[written:]
        os.fsync(fd)
        _check_file(os.fstat(fd), _file_acl(fd))
        os.close(fd)
        fd = None
        os.replace(temporary, FILE_NAME, src_dir_fd=directory, dst_dir_fd=directory)
        temporary = None
        os.fsync(directory)
    except (OSError, ValueError, TypeError, AttributeError):
        raise ProjectionUnavailable() from None
    finally:
        if fd is not None:
            os.close(fd)
        if temporary is not None and directory is not None:
            try:
                os.unlink(temporary, dir_fd=directory)
            except FileNotFoundError:
                pass
        if directory is not None:
            os.close(directory)
