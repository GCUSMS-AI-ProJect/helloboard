"""Authentication rejects missing credentials and verifies every AP update anew."""
import ctypes as C
import unittest
from unittest.mock import Mock, patch

from authentication import SystemAuthenticator
from pam_auth import Message, Response, PamConversation, authenticate


class AuthenticationTests(unittest.TestCase):
    def test_success_is_not_cached_and_null_passwords_are_rejected(self):
        auth = SystemAuthenticator('ubuntu')
        with patch('pam_auth.authenticate', side_effect=[True, False]) as verify:
            auth.verify('correct-password')
            with self.assertRaises(PermissionError): auth.verify('wrong-password')
            self.assertEqual(verify.call_count, 2)
        for invalid in ['', None, 'a\x00b', 'a' * 513]:
            with self.assertRaises(PermissionError): auth.verify(invalid)

    def test_failed_attempts_are_serialized_and_throttled(self):
        auth = SystemAuthenticator('ubuntu')
        with patch('pam_auth.authenticate', return_value=False) as verify:
            with self.assertRaises(PermissionError): auth.verify('wrong-password')
            with self.assertRaises(PermissionError): auth.verify('wrong-password')
            self.assertEqual(verify.call_count, 1)
        with auth.lock:
            with self.assertRaises(PermissionError): auth.verify('correct-password')

    def test_unavailable_pam_fails_closed(self):
        with patch('pam_auth.authenticate', side_effect=OSError('missing library')):
            with self.assertRaises(PermissionError): SystemAuthenticator('ubuntu').verify('password')

    def test_pam_conversation_and_account_checks_use_fresh_handles(self):
        """Use real C response allocation with a fake PAM ABI; no real login attempt."""
        original_cdll = C.CDLL
        libc = original_cdll(None)
        libc.free.argtypes, libc.free.restype = [C.c_void_p], None
        lib = Mock()
        credentials = []
        def start(service, user, conversation, handle):
            self.assertEqual(service, b'helloboard')
            self.assertEqual(user, b'ubuntu')
            conv = C.cast(conversation, C.POINTER(PamConversation)).contents
            prompts = [Message(1, b'Password:'), Message(2, b'User:'), Message(4, b'Info')]
            messages = (C.POINTER(Message) * 3)(*[C.pointer(m) for m in prompts])
            responses = C.POINTER(Response)()
            self.assertEqual(conv.callback(3, messages, C.byref(responses), None), 0)
            try:
                credentials.append([C.string_at(responses[i].text) for i in range(2)])
                self.assertFalse(responses[2].text)
            finally:
                for index in range(3): libc.free(responses[index].text)
                libc.free(C.cast(responses, C.c_void_p))
            C.cast(handle, C.POINTER(C.c_void_p))[0] = 123
            return 0
        lib.pam_start.side_effect = start
        lib.pam_authenticate.side_effect = [0, 7, 0]
        lib.pam_acct_mgmt.side_effect = [0, 13]
        with patch('pam_auth.find_library', return_value='test-libpam'), patch('pam_auth.C.CDLL', side_effect=lambda name: lib if name == 'test-libpam' else libc):
            self.assertTrue(authenticate('ubuntu', 'first-secret'))
            self.assertFalse(authenticate('ubuntu', 'bad-secret'))
            self.assertFalse(authenticate('ubuntu', 'expired-account-secret'))
        self.assertEqual(credentials[0], [b'first-secret', b'ubuntu'])
        self.assertEqual(lib.pam_start.call_count, 3)
        self.assertEqual(lib.pam_acct_mgmt.call_count, 2)
        self.assertEqual(lib.pam_end.call_count, 3)
        self.assertTrue(all(call.args[1] == 0x8001 for call in lib.pam_authenticate.call_args_list))


if __name__ == '__main__': unittest.main()
