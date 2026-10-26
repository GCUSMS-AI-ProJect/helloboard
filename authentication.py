"""Verify the device user through Linux PAM; browser grants live in Flask sessions.

No system password file or shell command is used by the application.
"""
import os
import threading
import time


def default_auth_user():
    import pwd
    if os.geteuid() != 0:
        return pwd.getpwuid(os.geteuid()).pw_name
    try:
        return pwd.getpwuid(1000).pw_name
    except KeyError:
        return pwd.getpwuid(os.geteuid()).pw_name


class SystemAuthenticator:
    available = True

    def __init__(self, username=None):
        import pwd
        self.username = username or default_auth_user()
        pwd.getpwnam(self.username)  # The account is configured by the service.
        self.lock = threading.Lock()
        self.retry_after = 0

    def verify(self, password):
        if not isinstance(password, str) or not password or len(password) > 512 or '\x00' in password:
            raise PermissionError('请输入系统登录密码。')
        if not self.lock.acquire(blocking=False):
            raise PermissionError('正在验证密码，请稍后再试。')
        try:
            if time.monotonic() < self.retry_after:
                raise PermissionError('请稍后重试系统密码验证。')
            try:
                from pam_auth import authenticate
                # PAM checks both the password and account expiry/lock policy.
                # A fresh PAM handle is used every time; credentials are not reset.
                valid = authenticate(self.username, password)
            except (ImportError, OSError):
                raise PermissionError('系统密码验证不可用，请检查 PAM 配置。') from None
            if not valid:
                self.retry_after = time.monotonic() + 3
                raise PermissionError('系统登录密码不正确或账户不可用。')
            self.retry_after = 0
        finally:
            self.lock.release()
