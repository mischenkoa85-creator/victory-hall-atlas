"""Deterministic projection checks; Linux ACL I/O is separately rehearsed."""
from datetime import datetime, timedelta, timezone
import json
import os
import stat
from types import SimpleNamespace
from unittest.mock import patch
import pytest
import atlas_power_projection as p

NOW = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)


def snapshot(**changes):
    value = dict(source='FRESH', grid='ABSENT', pv='GENERATING', pv_power_kw='2.30',
                 last_observed_at=NOW.isoformat(), last_received_at=NOW.isoformat(), age_s=0,
                 grid_absent_since=(NOW-timedelta(minutes=10)).isoformat(), grid_time_quality='CONFIRMED',
                 logger_sn='private-logger', raw_telemetry={'private': True}, credentials='never-export')
    return {**value, **changes}


def raw(**changes):
    return json.dumps({**p.project_snapshot(snapshot(), NOW), **changes}).encode()


def info(**changes):
    values = dict(st_mode=stat.S_IFREG | 0o640, st_uid=983, st_gid=975, st_nlink=1,
                  st_size=100, st_dev=1, st_ino=10, st_mtime_ns=10, st_ctime_ns=10)
    return SimpleNamespace(**{**values, **changes})


def test_allowlist_and_native_flat_contract():
    value = p.project_snapshot(snapshot(), NOW)
    assert set(value) == p.FIELDS
    assert value['source'] == 'FRESH' and value['grid'] == 'ABSENT'
    assert value['pv'] == 'GENERATING' and value['pv_power_kw'] == '2.3'
    assert value['freshness_s'] == 15
    assert not any(secret in json.dumps(value) for secret in ('private-logger', 'raw_telemetry', 'credentials'))


@pytest.mark.parametrize('field', ['last_observed_at', 'last_received_at'])
@pytest.mark.parametrize('value', [None, '', 'bad', 1, True, '2026-10-31T12:00:00',
                                 '2026-02-30T12:00:00Z', '2026-10-31T12:00:01Z'])
def test_invalid_missing_and_future_time_never_fresh(field, value):
    result = p.project_snapshot(snapshot(**{field: value}), NOW)
    assert result['source'] != 'FRESH'
    assert result['grid'] == result['pv'] == 'UNKNOWN'
    assert result['pv_power_kw'] is None and result['grid_absent_since'] is None


@pytest.mark.parametrize('seconds,expected', [(14.999, 'FRESH'), (15, 'STALE'), (29.999, 'STALE'), (30, 'OFFLINE')])
def test_freshness_recomputed_when_producer_stops(seconds, expected):
    result = p.decode_projection(raw(age_s=0), NOW+timedelta(seconds=seconds))
    assert result['source'] == expected and result['age_s'] == seconds
    if expected != 'FRESH':
        assert result['grid'] == result['pv'] == 'UNKNOWN' and result['pv_power_kw'] is None


def test_offline_status_is_never_promoted_by_recent_times():
    result = p.project_snapshot(snapshot(source='OFFLINE'), NOW)
    assert result['source'] == 'OFFLINE' and result['grid'] == 'UNKNOWN'


def test_unconfigured_pv_threshold_preserves_fresh_numeric_measurement_only():
    value = p.project_snapshot(snapshot(pv='UNKNOWN', pv_power_kw='2.30'), NOW)
    assert value['pv'] == 'UNKNOWN' and value['pv_power_kw'] == '2.3'
    assert p.decode_projection(json.dumps(value).encode(), NOW)['pv_power_kw'] == '2.3'
    stale = p.decode_projection(json.dumps(value).encode(), NOW+timedelta(seconds=15))
    assert stale['pv'] == 'UNKNOWN' and stale['pv_power_kw'] is None


def test_confirmed_outage_time_only_with_ordered_evidence():
    for changes in ({'grid_time_quality': 'UNCERTAIN'}, {'grid': 'PRESENT'},
                    {'grid_absent_since': (NOW+timedelta(seconds=1)).isoformat()}):
        assert p.project_snapshot(snapshot(**changes), NOW)['grid_absent_since'] is None


@pytest.mark.parametrize('value', ['NaN', 'Infinity', '-1', '1e999', True, 1, {}, '1e-9999'])
def test_invalid_power_is_never_displayed(value):
    assert p.project_snapshot(snapshot(pv_power_kw=value), NOW)['pv_power_kw'] is None


@pytest.mark.parametrize('changes', [{'logger_sn': 'private'}, {'freshness_s': 999}, {'freshness_s': True},
                                     {'age_s': True}, {'age_s': -1}, {'age_s': float('nan')},
                                     {'grid': 'ON'}, {'pv': False}, {'pv_power_kw': 2.3},
                                     {'last_received_at': 'bad'}, {'last_observed_at': 1}])
def test_strict_file_types_and_allowlist(changes):
    with pytest.raises(p.ProjectionUnavailable):
        p.decode_projection(raw(**changes), NOW)


def test_decode_rejects_duplicates_empty_oversize_and_nonobject():
    for value in (b'', b' '*4097, b'[]', b'{"source":"FRESH","source":"OFFLINE"}'):
        with pytest.raises(p.ProjectionUnavailable):
            p.decode_projection(value, NOW)


def test_decode_future_dates_are_not_fresh_even_with_claimed_zero_age():
    value = p.decode_projection(raw(last_received_at=(NOW+timedelta(seconds=1)).isoformat()), NOW)
    assert value['source'] != 'FRESH' and value['last_received_at'] is None


def test_exact_named_reader_acl_shape():
    p._check_file(info(), p.FILE_ACL)
    for change in ({'st_uid': 0}, {'st_gid': 986}, {'st_mode': stat.S_IFREG | 0o644},
                   {'st_mode': stat.S_IFLNK | 0o640}, {'st_nlink': 2}, {'st_size': 4097}):
        with pytest.raises(p.ProjectionUnavailable):
            p._check_file(info(**change), p.FILE_ACL)
    for acl in (None, b'', p.FILE_ACL[:-1], p.FILE_ACL.replace(b'\xda\x03\x00\x00', b'\xdb\x03\x00\x00')):
        with pytest.raises(p.ProjectionUnavailable):
            p._check_file(info(), acl)


def test_descriptor_read_rejects_modified_file():
    before = info(st_size=2)
    after = info(st_size=2, st_ctime_ns=11)
    with patch.object(p.os, 'fstat', side_effect=[before, after]), patch.object(p, '_file_acl', return_value=p.FILE_ACL), \
            patch.object(p.os, 'read', side_effect=[b'{}', b'']):
        with pytest.raises(p.ProjectionUnavailable):
            p._read_fd(9)


def test_reader_uses_fixed_nofollow_file_and_closes_on_failure():
    flags = {'O_NOFOLLOW': 0x100000, 'O_NONBLOCK': 0x200000, 'O_CLOEXEC': 0x400000}
    with patch.object(p, '_open_directory', return_value=9), patch.multiple(p.os, create=True, **flags), \
            patch.object(p.os, 'open', side_effect=OSError('symbolic link refused')) as opened, \
            patch.object(p.os, 'close') as closed:
        with pytest.raises(p.ProjectionUnavailable):
            p.read_projection(NOW)
        assert opened.call_args.args[0] == 'atlas-power.json'
        assert opened.call_args.args[1] & flags['O_NOFOLLOW']
        assert opened.call_args.kwargs == {'dir_fd': 9}
        closed.assert_called_once_with(9)


def test_naive_clock_is_rejected():
    with pytest.raises(p.ProjectionUnavailable):
        p.project_snapshot(snapshot(), NOW.replace(tzinfo=None))


def test_export_acl_is_set_and_verified_before_atomic_replace():
    calls = []
    content = bytearray()
    descriptor = info(st_size=0)
    def write(fd, value):
        calls.append('write')
        content.extend(value)
        descriptor.st_size += len(value)
        return len(value)
    def replace(*args, **kwargs):
        calls.append('replace')
        assert args[1] == p.FILE_NAME and kwargs == {'src_dir_fd': 9, 'dst_dir_fd': 9}
        p.decode_projection(bytes(content), NOW)
    with patch.object(p.sys, 'platform', 'linux'), \
            patch.multiple(p.os, create=True, O_NOFOLLOW=0x100000, O_NONBLOCK=0x200000, O_CLOEXEC=0x400000), \
            patch.object(p.os, 'geteuid', create=True, return_value=p.PRODUCER_UID), \
            patch.object(p.os, 'getegid', create=True, return_value=p.PRODUCER_GID), \
            patch.object(p, '_open_directory', return_value=9), \
            patch.object(p.os, 'open', side_effect=[FileNotFoundError(), 10]), \
            patch.object(p.os, 'setxattr', create=True, side_effect=lambda *a: calls.append('acl')), \
            patch.object(p, '_file_acl', return_value=p.FILE_ACL), \
            patch.object(p.os, 'fstat', return_value=descriptor), \
            patch.object(p.os, 'write', side_effect=write), \
            patch.object(p.os, 'fsync', side_effect=lambda *a: calls.append('fsync')), \
            patch.object(p.os, 'close'), patch.object(p.os, 'replace', side_effect=replace):
        p.export_snapshot(snapshot(), NOW)
    assert calls == ['acl', 'write', 'fsync', 'replace', 'fsync']


def test_export_acl_failure_preserves_previous_file_and_removes_only_new_temp():
    with patch.object(p.sys, 'platform', 'linux'), \
            patch.multiple(p.os, create=True, O_NOFOLLOW=0x100000, O_NONBLOCK=0x200000, O_CLOEXEC=0x400000), \
            patch.object(p.os, 'geteuid', create=True, return_value=p.PRODUCER_UID), \
            patch.object(p.os, 'getegid', create=True, return_value=p.PRODUCER_GID), \
            patch.object(p, '_open_directory', return_value=9), \
            patch.object(p.os, 'open', side_effect=[FileNotFoundError(), 10]), \
            patch.object(p.os, 'setxattr', create=True, side_effect=PermissionError()), \
            patch.object(p.os, 'close'), patch.object(p.os, 'replace') as replace, \
            patch.object(p.os, 'unlink') as unlink:
        with pytest.raises(p.ProjectionUnavailable):
            p.export_snapshot(snapshot(), NOW)
        replace.assert_not_called()
        assert unlink.call_args.args[0].startswith('.atlas-power-')
        assert unlink.call_args.args[0].endswith('.tmp')
        assert unlink.call_args.kwargs == {'dir_fd': 9}
