"""Local configuration; source packages contain no machine credentials or real host names."""
import ntpath
import os
import re


def remote_host():
    value = os.environ.get('NI_AGENT_REMOTE_HOST', 'labview-host')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,252}', value):
        raise ValueError('NI_AGENT_REMOTE_HOST must be a host name or SSH config alias')
    return value


def windows_root():
    value = os.environ.get('NI_AGENT_WINDOWS_ROOT', r'C:\ZhixinNI_Agent')
    unsafe = '\r\n\x00\'"`;$&|()<>'
    if (not re.match(r'^[A-Za-z]:\\', value) or any(c in value for c in unsafe)
            or '..' in value.replace('/', '\\').split('\\')):
        raise ValueError('NI_AGENT_WINDOWS_ROOT must be an absolute, shell-safe Windows path')
    return ntpath.normpath(value)


def remote_enabled():
    return os.environ.get("NI_AGENT_ENABLE_REMOTE", "").lower() in ("1", "true")


def require_remote():
    if not remote_enabled():
        raise RuntimeError('Remote execution is disabled. Configure the host and explicitly set NI_AGENT_ENABLE_REMOTE=1')
    remote_host()
    windows_root()
