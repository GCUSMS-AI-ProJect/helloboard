"""Small process-control boundary: fresh credentials live in the HTTP handler.

Never signal a raw PID: an open pidfd pins the process while its start time is
checked against the selected sample. There is deliberately no kill(PID) fallback.
"""
import os
import platform
from pathlib import Path
import signal
import threading

from controller import BusyError
from system_metrics import process_stat


class ProcessManager:
    MAX_BATCH = 32
    CRITICAL_NAMES = frozenset({
        'systemd', 'init', 'NetworkManager', 'wpa_supplicant', 'sshd', 'sshd-session',
        'dbus-daemon', 'dbus-broker', 'systemd-network', 'systemd-resolve',
    })

    def __init__(self, metrics, *, preview=False, proc='/proc', allow_control=True):
        self.metrics, self.preview, self.proc = metrics, preview, Path(proc)
        self.lock = threading.Lock()
        self.allow_control = allow_control

    @staticmethod
    def supported():
        return platform.system() == 'Linux' and hasattr(os, 'pidfd_open') and hasattr(signal, 'pidfd_send_signal')

    def _read(self, pid):
        return process_stat((self.proc / str(pid) / 'stat').read_text(), os.sysconf('SC_PAGE_SIZE'))

    def _ancestors(self):
        protected = {1, os.getpid(), os.getppid()}
        pid = os.getppid()
        while pid > 1:
            try:
                parent = self._read(pid)['parent']
            except (OSError, ValueError, IndexError):
                break
            if parent <= 1 or parent in protected:
                break
            protected.add(parent)
            pid = parent
        return protected

    def _reason(self, item, protected):
        if (item['pid'] in protected or item['name'] in self.CRITICAL_NAMES
                or item['flags'] & 0x00200000):  # PF_KTHREAD
            return '受保护的系统进程'
        if item['state'] in {'Z', 'X', 'x'}:
            return '进程已退出'
        return ''

    def snapshot(self):
        supported = self.supported() and self.allow_control
        protected = self._ancestors() if supported else set()
        items = []
        for item in self.metrics.process_snapshot():
            reason = self._reason(item, protected) if supported else '当前系统仅支持查看进程。'
            items.append({key: item[key] for key in ('pid', 'started', 'name', 'cpu_percent', 'memory')}
                         | {'selectable': not reason, 'reason': reason})
        return dict(items=items, preview=self.preview, supported=supported,
                    max_batch=self.MAX_BATCH)

    def validate(self, payload):
        if not isinstance(payload, dict):
            raise ValueError('请求格式不正确。')
        action, targets = payload.get('action'), payload.get('targets')
        if action not in ('terminate', 'kill'):
            raise ValueError('请选择终止方式。')
        if not isinstance(targets, list) or not 1 <= len(targets) <= self.MAX_BATCH:
            raise ValueError('每次请选择 1–32 个进程。')
        seen = set()
        for target in targets:
            if (not isinstance(target, dict) or type(target.get('pid')) is not int
                    or type(target.get('started')) is not int or target['pid'] <= 0
                    or target['started'] < 0 or target['pid'] > 2**31 - 1):
                raise ValueError('进程标识不正确，请刷新列表。')
            if target['pid'] in seen:
                raise ValueError('请勿重复选择同一个进程。')
            seen.add(target['pid'])
        return action, targets

    def terminate(self, payload):
        action, targets = self.validate(payload)
        if self.preview:
            raise PermissionError('预览模式不允许终止进程。')
        if not self.supported() or not self.allow_control:
            raise PermissionError('当前系统不支持安全终止进程。')
        if not self.lock.acquire(blocking=False):
            raise BusyError('正在终止进程，请稍后重试。')
        try:
            protected = self._ancestors()
            results = []
            for target in targets:
                pid, fd = target['pid'], None
                result = dict(pid=pid, started=target['started'])
                try:
                    fd = os.pidfd_open(pid, 0)
                    current = self._read(pid)
                    reason = self._reason(dict(current, pid=pid), protected)
                    if current['started'] != target['started']:
                        result.update(status='changed', message='进程已变化，请重新选择。')
                    elif reason:
                        result.update(status='protected', message=reason)
                    else:
                        signal.pidfd_send_signal(fd, signal.SIGTERM if action == 'terminate' else signal.SIGKILL)
                        result.update(status='sent', message='已发送退出请求' if action == 'terminate' else '已发送强制终止信号')
                except (ProcessLookupError, FileNotFoundError):
                    result.update(status='exited', message='进程已退出')
                except PermissionError:
                    result.update(status='denied', message='没有权限终止此进程。')
                except (OSError, ValueError, IndexError):
                    result.update(status='unavailable', message='暂时无法终止此进程。')
                finally:
                    if fd is not None:
                        os.close(fd)
                results.append(result)
            return dict(results=results)
        finally:
            self.lock.release()
