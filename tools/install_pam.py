"""Install a PAM include policy for the host's existing distro policy.

No authentication policy is invented when the distro layout is unknown.
"""
from pathlib import Path


def install(directory=Path('/etc/pam.d')):
    directory = Path(directory)
    if all((directory / name).is_file() for name in ('common-auth', 'common-account')):
        policy = '# HelloBoard system account verification\n@include common-auth\n@include common-account\n'
    elif (directory / 'system-auth').is_file():
        policy = '# HelloBoard system account verification\nauth include system-auth\naccount include system-auth\n'
    else:
        print('未找到受支持的系统 PAM 策略，账号验证暂不启用。')
        return False
    target = directory / 'helloboard'
    target.write_text(policy)
    target.chmod(0o644)
    return True


if __name__ == '__main__':
    install()
