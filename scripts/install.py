#!/usr/bin/env python3
"""Install the versioned personal assistant on George's Termux/Debian phone."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

REPO = Path(__file__).resolve().parents[1]
PHONE_HOME = Path('/data/data/com.termux/files/home')
PREFIX = Path('/data/data/com.termux/files/usr')
DEBIAN = PREFIX / 'var/lib/proot-distro/containers/debian/rootfs'
BRIDGE = DEBIAN / 'root/.vapi/bridge'
SHARE = DEBIAN / 'root/.local/share/phone-errands'
BOOT = PHONE_HOME / '.termux/boot/16-voice-line'
TMUX = str(PREFIX / 'bin/tmux')
PROOT = str(PREFIX / 'bin/proot-distro')


def run(args, **kwargs):
    return subprocess.run(args, check=True, text=True, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--sync-vapi', action='store_true')
    args = parser.parse_args()
    if not args.apply:
        print('Install personal voice code, phone and support-chat commands, prompts, and keeper. Use --apply to install; add --sync-vapi to apply the personal assistant settings.')
        return
    revision = subprocess.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True).strip()
    if subprocess.check_output(['git', '-C', str(REPO), 'status', '--porcelain'], text=True).strip():
        raise RuntimeError('Commit the source before installing so the running revision has a receipt.')
    config = json.loads((REPO / 'config/personal-assistant.json').read_text())
    # Read the one personal assistant's calls before a service restart.
    run([PROOT, 'login', 'debian', '--', 'python3', str(REPO / 'scripts/check-idle.py')])
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup = PHONE_HOME / '.local/state/phone-errands/deployments' / stamp
    backup.mkdir(parents=True, mode=0o700)
    (BRIDGE / 'MAINTENANCE').touch()
    lock = PHONE_HOME / '.agent-bridge/voice-line.lock'
    if lock.exists():
        pid = int(lock.read_text().strip())
        try:
            command = Path(f'/proc/{pid}/cmdline').read_bytes().replace(b'\0', b' ').decode()
            if '16-voice-line' in command:
                os.kill(pid, signal.SIGTERM)
        except (FileNotFoundError, ProcessLookupError):
            pass
    installed = []
    try:
        run([PROOT, 'login', 'debian', '--', 'python3', str(REPO / 'voice/service.py'), 'stop'])
        subprocess.run([TMUX, '-L', 'vapi-line', 'kill-session', '-t', 'vsrv'], capture_output=True)
        def copy(source, target, executable=False):
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() or target.is_symlink():
                saved = backup / str(target).lstrip('/')
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, saved, follow_symlinks=False)
                if target.is_symlink():
                    target.unlink()
            shutil.copy2(source, target)
            if executable:
                target.chmod(0o700)
            installed.append({'path': str(target), 'sha256': hashlib.sha256(target.read_bytes()).hexdigest()})
        for folder in ['voice', 'bin', 'prompts', 'config', 'scripts']:
            for source in (REPO / folder).rglob('*'):
                if source.is_file() and '__pycache__' not in source.parts:
                    copy(source, SHARE / source.relative_to(REPO))
        for name in ['phone-ask', 'phone-do', 'assistant', 'support-chat', 'assistant_records.py', 'README.md']:
            copy(REPO / name, SHARE / name, name in ['phone-ask', 'phone-do', 'assistant', 'support-chat'])
        for source in (REPO / 'voice').iterdir():
            if source.is_file():
                copy(source, BRIDGE / source.name, source.suffix == '.sh')
        copy(REPO / 'prompts/brain-errand.md', BRIDGE / 'brain_instructions.txt')
        copy(REPO / 'prompts/voice.txt', DEBIAN / 'root/.vapi/fastline_context.txt')
        copy(REPO / 'bin/voice-tmux', BRIDGE / 'bin/tmux', True)
        for name in ['voice-session', 'voice-use', 'voice-list']:
            copy(REPO / 'bin' / name, DEBIAN / 'usr/local/bin' / name, True)
        for name in ['phone-ask', 'phone-do', 'assistant', 'support-chat']:
            target = DEBIAN / 'usr/local/bin' / name
            if target.exists() or target.is_symlink():
                saved = backup / 'commands' / name
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, saved, follow_symlinks=False)
                target.unlink()
            target.symlink_to('/root/.local/share/phone-errands/' + name)
            wrapper = PHONE_HOME / '.local/bin' / name
            wrapper.parent.mkdir(parents=True, exist_ok=True)
            if wrapper.exists():
                saved = backup / 'native-commands' / name
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(wrapper, saved)
            wrapper.write_text('#!/data/data/com.termux/files/usr/bin/sh\n# phone-errands launcher\nexec /data/data/com.termux/files/usr/bin/proot-distro login --work-dir "$PWD" debian -- /usr/local/bin/' + name + ' "$@"\n')
            wrapper.chmod(0o700)
        copy(REPO / 'bin/16-voice-line', BOOT, True)
        (BRIDGE / 'REVISION').write_text(revision + '\n')
        (BRIDGE / 'WANTED').touch()
        (BRIDGE / 'MAINTENANCE').unlink()
        if subprocess.run([TMUX, '-L', 'vapi-line', 'has-session', '-t', 'control'], capture_output=True).returncode:
            run([TMUX, '-L', 'vapi-line', 'new-session', '-d', '-s', 'control'])
        keeper = 'VOICE_LINE_FIRST_WAIT=0 /data/data/com.termux/files/usr/bin/sh ' + str(BOOT)
        run([TMUX, '-L', 'vapi-line', 'respawn-pane', '-k', '-t', 'control', keeper])
        if args.sync_vapi:
            run([PROOT, 'login', 'debian', '--', 'python3', '/root/.local/share/phone-errands/scripts/sync-vapi.py', '--apply'])
        receipt = {'revision': revision, 'installedAt': stamp, 'files': installed, 'personalAssistantId': config['assistantId']}
        (backup / 'receipt.json').write_text(json.dumps(receipt, indent=2))
        print(json.dumps({'revision': revision, 'deploymentReceipt': str(backup / 'receipt.json')}, indent=2))
    except Exception:
        print('Deployment stopped. Backup:', backup)
        raise


if __name__ == '__main__':
    main()
