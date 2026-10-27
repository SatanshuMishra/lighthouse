import datetime
import errno
import fcntl
import json
import math
import os
import pwd
import re
import tempfile
from collections.abc import Mapping

FORMAT_VERSION = 1
ROOT_VARIABLE = 'PLUGIN_METRICS_DIR'
PARENT_VARIABLE = 'PLUGIN_METRICS_PARENT'
SESSION_VARIABLE = 'CLAUDE_CODE_SESSION_ID'
DEFAULT_FOLDER = '.plugin-metrics'
ENVELOPE = ('v', 'ts', 'plugin', 'plugin_version', 'kind', 'event', 'run', 'parent', 'session', 'repo')
KINDS = ('event', 'summary')
SUMMARY_EVENT = 'run.summary'
TOKEN_KINDS = ('input', 'cache_write_5m', 'cache_write_1h', 'cache_read', 'output')
KEEP_EVENT_RUNS = 100
KEEP_SUMMARY_RUNS = 1000
WARNING_PREFIX = 'metrics not written: '
PLUGIN_PREFIX = 'plugin='
KIND_PREFIX = 'kind='
REPO_PREFIX = 'repo='

TIMESTAMP_FORMAT = '%Y-%m-%dT%H:%M:%SZ'
RUN_STAMP_FORMAT = '%Y%m%dT%H%M%SZ'
EVENT_SUFFIX = '.jsonl'
SUMMARY_SUFFIX = '.json'
CATALOGUE_FILE = 'catalogue.json'
TEMPORARY_PREFIX = '.'
TEMPORARY_SUFFIX = '.tmp'
FILE_MODE = 0o600
FOLDER_MODE = 0o700
NAME_LIMIT = 120
EARLIEST_START = ''
RUN_PATTERN = re.compile('[a-z0-9][a-z0-9.-]*(\\.[0-9]{8}T[0-9]{6}Z)?')
PLUGIN_PATTERN = re.compile('[a-z][a-z0-9-]*')
FIELD_PATTERN = re.compile('[a-z][a-z0-9_]*')
INTEGER_KEY_PATTERN = re.compile('-?(0|[1-9][0-9]*)')
FORBIDDEN_REPO_CHARACTER = re.compile('[/=\x00-\x1f]')
LONE_SURROGATE = re.compile('[\ud800-\udfff]')
DECIMAL_EXPONENT_FLOOR = -6
DECIMAL_EXPONENT_CEILING = 21


def _environment(environ):
    return os.environ if environ is None else environ


def _home(environ):
    return environ.get('HOME') or os.environ.get('HOME') or pwd.getpwuid(os.getuid()).pw_dir


def store_root(environ):
    chosen = environ.get(ROOT_VARIABLE, '')
    return chosen if chosen else os.path.join(_home(environ), DEFAULT_FOLDER)


def _utc(moment):
    aware = moment.replace(tzinfo=datetime.timezone.utc) if moment.tzinfo is None else moment
    return aware.astimezone(datetime.timezone.utc)


def _timestamp(now):
    return _utc(datetime.datetime.now(datetime.timezone.utc) if now is None else now).strftime(TIMESTAMP_FORMAT)


def run_id(name, start):
    return name + '.' + _utc(start).strftime(RUN_STAMP_FORMAT)


def _kind_folder(root, plugin, kind, repo):
    return os.path.join(root, PLUGIN_PREFIX + plugin, KIND_PREFIX + kind, REPO_PREFIX + repo)


def event_path(root, plugin, repo, run):
    return os.path.join(_kind_folder(root, plugin, 'event', repo), run + EVENT_SUFFIX)


def summary_path(root, plugin, repo, run):
    return os.path.join(_kind_folder(root, plugin, 'summary', repo), run + SUMMARY_SUFFIX)


def catalogue_path(root, plugin):
    return os.path.join(root, PLUGIN_PREFIX + plugin, CATALOGUE_FILE)


def _significant_digits(magnitude):
    mantissa, _, exponent = repr(magnitude).partition('e')
    whole, _, fraction = mantissa.partition('.')
    written = whole + fraction
    stripped = written.lstrip('0')
    point = len(whole) + int(exponent or '0') - (len(written) - len(stripped))
    return stripped.rstrip('0'), point


def _scientific_text(digits, point):
    exponent = point - 1
    sign = '+' if exponent >= 0 else '-'
    body = digits if len(digits) == 1 else digits[0] + '.' + digits[1:]
    return body + 'e' + sign + str(abs(exponent))


def _magnitude_text(magnitude):
    digits, point = _significant_digits(magnitude)
    count = len(digits)
    if count <= point <= DECIMAL_EXPONENT_CEILING:
        return digits + '0' * (point - count)
    if 0 < point <= DECIMAL_EXPONENT_CEILING:
        return digits[:point] + '.' + digits[point:]
    if DECIMAL_EXPONENT_FLOOR < point <= 0:
        return '0.' + '0' * -point + digits
    return _scientific_text(digits, point)


def _float_text(value):
    if not math.isfinite(value):
        return 'null'
    if value == 0:
        return '0'
    return ('-' if value < 0 else '') + _magnitude_text(abs(value))


def _string_text(value):
    return LONE_SURROGATE.sub(lambda found: '\\u%04x' % ord(found.group()), json.dumps(value, ensure_ascii=False))


def _value_text(value):
    if value is None:
        return 'null'
    if value is True:
        return 'true'
    if value is False:
        return 'false'
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return _float_text(value)
    if isinstance(value, str):
        return _string_text(value)
    if isinstance(value, Mapping):
        return '{' + ','.join(_string_text(key) + ':' + _value_text(item) for key, item in value.items()) + '}'
    if isinstance(value, (list, tuple)):
        return '[' + ','.join(_value_text(item) for item in value) + ']'
    raise TypeError('a value of type ' + type(value).__name__ + ' has no JSON form')


def encoded_line(record):
    return (_value_text(record) + '\n').encode('utf-8')


def _refused(subject, rule):
    return WARNING_PREFIX + subject + ': ' + rule


def _run_refusal(run):
    if not isinstance(run, str) or run == '':
        return _refused('run', 'must not be empty')
    if len(run) > NAME_LIMIT:
        return _refused('run', 'must be at most 120 characters')
    if not RUN_PATTERN.fullmatch(run):
        return _refused('run', 'must be lowercase letters, digits, dots and hyphens starting with a letter or digit, optionally ending in a .YYYYMMDDTHHMMSSZ start')
    return None


def _plugin_refusal(plugin):
    if not isinstance(plugin, str) or not PLUGIN_PATTERN.fullmatch(plugin):
        return _refused('plugin', 'must be lowercase letters, digits and hyphens starting with a letter')
    return None


def _repo_refusal(repo):
    if not isinstance(repo, str) or repo == '':
        return _refused('repo', 'must not be empty')
    if len(repo) > NAME_LIMIT:
        return _refused('repo', 'must be at most 120 characters')
    if repo.startswith('.'):
        return _refused('repo', 'must not start with a dot')
    if FORBIDDEN_REPO_CHARACTER.search(repo):
        return _refused('repo', 'must not hold a slash, an equals sign or a control character')
    return None


def _field_refusal(name):
    if not isinstance(name, str) or not FIELD_PATTERN.fullmatch(name):
        return _refused('field ' + str(name), 'must be lowercase letters, digits and underscores starting with a letter')
    if name in ENVELOPE:
        return _refused('field ' + name, 'must not be an envelope key')
    return None


def _key_refusal(value):
    if isinstance(value, Mapping):
        integer_key = next((key for key in value if not isinstance(key, str) or INTEGER_KEY_PATTERN.fullmatch(key)), None)
        if integer_key is not None:
            return _refused('key ' + str(integer_key), 'must not be an integer string')
        return next((refusal for refusal in map(_key_refusal, value.values()) if refusal is not None), None)
    if isinstance(value, (list, tuple)):
        return next((refusal for refusal in map(_key_refusal, value) if refusal is not None), None)
    return None


def _first_refusal(refusals):
    return next((refusal for refusal in refusals if refusal is not None), None)


def _line_refusal(plugin, repo, run, fields):
    return _first_refusal((
        _run_refusal(run),
        _plugin_refusal(plugin),
        _repo_refusal(repo),
        _first_refusal(map(_field_refusal, fields)),
        _key_refusal(fields),
    ))


def _record(plugin, plugin_version, repo, run, kind, event, fields, environ, now):
    envelope = (
        FORMAT_VERSION,
        _timestamp(now),
        plugin,
        plugin_version,
        kind,
        event,
        run,
        environ.get(PARENT_VARIABLE, '') or None,
        environ.get(SESSION_VARIABLE, '') or None,
        repo,
    )
    return dict(tuple(zip(ENVELOPE, envelope)) + tuple(fields.items()))


def _failed(path, error):
    return WARNING_PREFIX + str(path) + ': ' + (error.strerror or str(error))


def _ensure_folder(folder):
    if os.path.isdir(folder):
        return
    _ensure_folder(os.path.dirname(folder))
    try:
        os.mkdir(folder, FOLDER_MODE)
    except FileExistsError:
        if not os.path.isdir(folder):
            raise


def _append(path, line):
    _ensure_folder(os.path.dirname(os.path.abspath(path)))
    descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, FILE_MODE)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        before = os.fstat(descriptor).st_size
        written = os.write(descriptor, line)
        if written != len(line):
            if os.fstat(descriptor).st_size == before + written:
                os.ftruncate(descriptor, before)
            raise OSError(errno.EIO, 'wrote ' + str(written) + ' of ' + str(len(line)) + ' bytes')
    finally:
        os.close(descriptor)


def _replace(path, content):
    folder = os.path.dirname(os.path.abspath(path))
    _ensure_folder(folder)
    descriptor, temporary = tempfile.mkstemp(prefix=TEMPORARY_PREFIX, suffix=TEMPORARY_SUFFIX, dir=folder)
    try:
        with os.fdopen(descriptor, 'wb') as handle:
            handle.write(content)
        os.replace(temporary, path)
    except BaseException:
        if os.path.exists(temporary):
            os.remove(temporary)
        raise


def _encoded_or_refusal(record):
    try:
        return encoded_line(record), None
    except (TypeError, ValueError, RecursionError) as error:
        return None, _refused('fields', str(error))


def append_event(plugin, plugin_version, repo, run, event, fields, environ=None, now=None):
    refusal = _line_refusal(plugin, repo, run, fields)
    if refusal is not None:
        return refusal
    chosen = _environment(environ)
    line, unencodable = _encoded_or_refusal(_record(plugin, plugin_version, repo, run, 'event', event, fields, chosen, now))
    if unencodable is not None:
        return unencodable
    path = event_path(store_root(chosen), plugin, repo, run)
    try:
        _append(path, line)
    except OSError as error:
        return _failed(path, error)
    return None


def write_summary(plugin, plugin_version, repo, run, fields, environ=None, now=None):
    refusal = _line_refusal(plugin, repo, run, fields)
    if refusal is not None:
        return refusal
    chosen = _environment(environ)
    line, unencodable = _encoded_or_refusal(_record(plugin, plugin_version, repo, run, 'summary', SUMMARY_EVENT, fields, chosen, now))
    if unencodable is not None:
        return unencodable
    root = store_root(chosen)
    path = summary_path(root, plugin, repo, run)
    try:
        _replace(path, line)
    except OSError as error:
        return _failed(path, error)
    try:
        prune(root, plugin, repo)
    except OSError as error:
        return _failed(error.filename or os.path.dirname(path), error)
    return None


def _catalogue_text(catalogue):
    return (json.dumps(catalogue, indent=2, ensure_ascii=False) + '\n').encode('utf-8')


def _current_content(path):
    try:
        with open(path, 'rb') as handle:
            return handle.read()
    except FileNotFoundError:
        return None


def write_catalogue(plugin, catalogue, environ=None):
    refusal = _first_refusal((_plugin_refusal(plugin), _key_refusal(catalogue)))
    if refusal is not None:
        return refusal
    try:
        content = _catalogue_text(catalogue)
    except (TypeError, ValueError, RecursionError) as error:
        return _refused('catalogue', str(error))
    path = catalogue_path(store_root(_environment(environ)), plugin)
    try:
        if _current_content(path) != content:
            _replace(path, content)
    except OSError as error:
        return _failed(path, error)
    return None


def _run_names(folder, suffix):
    try:
        names = os.listdir(folder)
    except OSError:
        return frozenset()
    return frozenset(
        name[:-len(suffix)]
        for name in names
        if name.endswith(suffix) and RUN_PATTERN.fullmatch(name[:-len(suffix)]) and len(name) - len(suffix) <= NAME_LIMIT
    )


def _first_ts(path):
    try:
        with open(path, encoding='utf-8') as handle:
            record = json.loads(handle.readline())
    except (OSError, ValueError):
        return None
    ts = record.get('ts') if isinstance(record, dict) else None
    return ts if isinstance(ts, str) else None


def _modified(path):
    try:
        seconds = os.stat(path).st_mtime
    except OSError:
        return None
    return datetime.datetime.fromtimestamp(seconds, datetime.timezone.utc).strftime(TIMESTAMP_FORMAT)


def _start(root, plugin, repo, run):
    paths = (event_path(root, plugin, repo, run), summary_path(root, plugin, repo, run))
    return next(
        (start for start in map(_first_ts, paths) if start is not None),
        next((moment for moment in map(_modified, paths) if moment is not None), EARLIEST_START),
    )


def _removed(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        return False
    return True


def prune(root, plugin, repo, keep_events=KEEP_EVENT_RUNS, keep_summaries=KEEP_SUMMARY_RUNS):
    with_events = _run_names(_kind_folder(root, plugin, 'event', repo), EVENT_SUFFIX)
    with_summaries = _run_names(_kind_folder(root, plugin, 'summary', repo), SUMMARY_SUFFIX)
    newest_first = sorted(
        with_events | with_summaries,
        key=lambda run: (_start(root, plugin, repo, run), run),
        reverse=True,
    )
    doomed = tuple(
        path
        for index, run in enumerate(newest_first)
        for path, present, keep in (
            (event_path(root, plugin, repo, run), run in with_events, keep_events),
            (summary_path(root, plugin, repo, run), run in with_summaries, keep_summaries),
        )
        if present and index >= keep
    )
    return tuple(path for path in doomed if _removed(path))
