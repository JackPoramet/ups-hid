"""Provision notification-only NUT monitoring without enabling local shutdown."""
from __future__ import annotations

import argparse
import base64
import configparser
import os
from pathlib import Path
import re
import secrets
import tempfile

BEGIN = '# BEGIN ENEREX NOTIFICATION MONITOR\n'
END = '# END ENEREX NOTIFICATION MONITOR\n'
SAVED = '# ENEREX ORIGINAL DIRECTIVE '
USER = 'enerex-monitor'
SERVICE_STATE = 'etc/nut/.enerex-monitor-original-enablement'


def _unmanage(text):
    if text.count(BEGIN) != text.count(END) or text.count(BEGIN)>1:
        raise ValueError('Malformed managed NUT configuration')
    output, inside = [], False
    for line in text.splitlines(keepends=True):
        if line == BEGIN:
            inside = True
        elif line == END:
            if not inside:
                raise ValueError('Malformed managed NUT configuration')
            inside = False
        elif not inside:
            if line.startswith(SAVED):
                try:
                    line = base64.b64decode(line[len(SAVED):].strip(), validate=True).decode('utf-8')
                except (ValueError, UnicodeError) as exc:
                    raise ValueError('Malformed original directive record') from exc
            output.append(line)
    if inside:
        raise ValueError('Unterminated managed NUT configuration')
    return ''.join(output)


def bridge_ups_name(root):
    path = Path(root)/'etc/nut/ups.conf'
    config = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=('#',))
    config.read_string('[GLOBAL]\n'+path.read_text(encoding='utf-8'))
    sections = [s for s in config.sections() if s != 'GLOBAL']
    if len(sections) != 1 or config.get(sections[0], 'driver', fallback='') != 'enerex':
        raise ValueError('Migration requires exactly one Enerex UPS; native/multi-UPS config is unchanged')
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}',sections[0]):
        raise ValueError('Invalid UPS name')
    if config.get(sections[0], 'port', fallback='') != '/etc/nut/myups.dev':
        raise ValueError('Enerex migration requires /etc/nut/myups.dev snapshot port')
    return sections[0]


def _atomic(path, text, owner_group):
    if path.is_symlink():
        raise ValueError('Refusing a symlink NUT configuration path')
    if path.exists() and path.read_text(encoding='utf-8') == text:
        return False
    if path.exists():
        backup = Path(str(path)+'.enerex-before-notify')
        if not backup.exists():
            fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd,'wb') as stream:
                stream.write(path.read_bytes())
    fd, name = tempfile.mkstemp(prefix='.enerex-config-', dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8',newline='\n') as stream:
            stream.write(text)
        os.chmod(name,0o640)
        if owner_group:
            import grp
            os.chown(name,0,grp.getgrnam(owner_group).gr_gid)
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)
    return True


def configure_notification_monitor(root, ups_name, *, owner_group='nut', dry_run=False):
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}',ups_name):
        raise ValueError('Invalid UPS name')
    conf = Path(root)/'etc/nut'
    monitor_path, users_path = conf/'upsmon.conf', conf/'upsd.users'
    if monitor_path.is_symlink() or users_path.is_symlink():
        raise ValueError('Refusing a symlink NUT configuration path')
    old_monitor, old_users = monitor_path.read_text(encoding='utf-8'), users_path.read_text(encoding='utf-8')
    monitor, users = _unmanage(old_monitor), _unmanage(old_users)
    if re.search(r'^\s*MONITOR\s+',monitor,re.MULTILINE):
        raise ValueError('Existing independent MONITOR requires explicit migration')
    if re.search(r'^\s*NOTIFYCMD\s+|^\s*NOTIFYFLAG\s+.*\bEXEC\b',monitor,re.MULTILINE):
        raise ValueError('Existing executable notification hooks require explicit review')
    if re.search(r'^\s*\[\s*"?enerex-monitor"?\s*\]\s*(?:#.*)?$',users,re.MULTILINE):
        raise ValueError('Independent enerex-monitor user already exists')
    if BEGIN in old_users:
        managed = old_users.split(BEGIN,1)[1].split(END,1)[0]
        match = re.search(r'^\s*password\s*=\s*([a-f0-9]{48})\s*$',managed,re.MULTILINE)
        if not match:
            raise ValueError('Managed monitor credentials are invalid')
        secret = match.group(1)
    else:
        secret = secrets.token_hex(24)
    lines=[]
    for line in monitor.splitlines(keepends=True):
        if re.match(r'^\s*(MINSUPPLIES|SHUTDOWNCMD|POWERDOWNFLAG)\s+',line):
            lines.append(SAVED+base64.b64encode(line.encode()).decode()+'\n')
        else:
            lines.append(line)
    monitor=''.join(lines)
    if monitor and not monitor.endswith('\n'):monitor+='\n'
    monitor += (BEGIN+'MINSUPPLIES 0\nSHUTDOWNCMD "/bin/false"\n'
                +f'MONITOR {ups_name}@localhost 0 {USER} {secret} slave\n'+END)
    if users and not users.endswith('\n'):users+='\n'
    users += BEGIN+f'[{USER}]\npassword = {secret}\nupsmon slave\n'+END
    if dry_run:
        return monitor != old_monitor or users != old_users
    changed_users=_atomic(users_path,users,owner_group)
    changed_monitor=_atomic(monitor_path,monitor,owner_group)
    return changed_users or changed_monitor


def remove_notification_monitor(root, *, owner_group='nut'):
    for name in ('upsmon.conf','upsd.users'):
        path=Path(root)/'etc/nut'/name
        if path.exists():
            _atomic(path,_unmanage(path.read_text(encoding='utf-8')),owner_group)


def original_monitor_service_state(root):
    path=Path(root)/SERVICE_STATE
    if not path.exists():return ''
    if path.is_symlink():raise ValueError('Refusing a symlink service-state record')
    state=path.read_text(encoding='utf-8').strip()
    if state not in ('enabled','disabled','enabled-runtime'):
        raise ValueError('Invalid original monitor service state')
    return state


def record_monitor_service_state(root, state):
    if state not in ('enabled','disabled','enabled-runtime'):
        raise ValueError('Unsupported monitor enablement state; no services changed')
    if not original_monitor_service_state(root):
        _atomic(Path(root)/SERVICE_STATE,state+'\n',None)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path('/'))
    parser.add_argument('--check',action='store_true')
    parser.add_argument('--remove',action='store_true')
    parser.add_argument('--record-service-state',choices=('enabled','disabled','enabled-runtime'))
    parser.add_argument('--original-service-state',action='store_true')
    args=parser.parse_args(argv)
    if args.record_service_state:
        record_monitor_service_state(args.root,args.record_service_state)
        print('Recorded original monitor service enablement')
        return
    if args.original_service_state:
        print(original_monitor_service_state(args.root))
        return
    if args.remove:
        remove_notification_monitor(args.root)
        print('Removed owned notification-monitor configuration')
        return
    name=bridge_ups_name(args.root)
    configure_notification_monitor(args.root,name,dry_run=args.check)
    print('Notification-only monitor '+('preflight valid' if args.check else 'configured')+' for '+name)


if __name__=='__main__':
    main()
