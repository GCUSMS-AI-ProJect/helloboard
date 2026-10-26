"""Small Linux-PAM adapter using the system library, with no Python dependency.

ABI definitions follow Linux-PAM's pam_appl.h and _pam_types.h. PAM owns the
C-allocated conversation responses; Python keeps the callback alive until end.
"""
import ctypes as C
from ctypes.util import find_library


class Message(C.Structure):
    _fields_ = [('style', C.c_int), ('text', C.c_char_p)]


class Response(C.Structure):
    _fields_ = [('text', C.c_void_p), ('code', C.c_int)]


Conversation = C.CFUNCTYPE(C.c_int, C.c_int, C.POINTER(C.POINTER(Message)),
                          C.POINTER(C.POINTER(Response)), C.c_void_p)


class PamConversation(C.Structure):
    _fields_ = [('callback', Conversation), ('data', C.c_void_p)]


def authenticate(username, password):
    lib = C.CDLL(find_library('pam') or 'libpam.so.0')
    libc = C.CDLL(None)
    libc.calloc.argtypes, libc.calloc.restype = [C.c_size_t, C.c_size_t], C.c_void_p
    libc.strdup.argtypes, libc.strdup.restype = [C.c_char_p], C.c_void_p
    libc.free.argtypes, libc.free.restype = [C.c_void_p], None
    lib.pam_start.argtypes = [C.c_char_p, C.c_char_p, C.POINTER(PamConversation), C.POINTER(C.c_void_p)]
    lib.pam_authenticate.argtypes = [C.c_void_p, C.c_int]
    lib.pam_acct_mgmt.argtypes = [C.c_void_p, C.c_int]
    lib.pam_end.argtypes = [C.c_void_p, C.c_int]
    for name in ('pam_start', 'pam_authenticate', 'pam_acct_mgmt', 'pam_end'):
        getattr(lib, name).restype = C.c_int
    credentials = {1: password.encode('utf-8'), 2: username.encode('utf-8')}

    @Conversation
    def converse(count, messages, output, _data):
        if not 1 <= count <= 32:
            return 19  # PAM_CONV_ERR
        block = libc.calloc(count, C.sizeof(Response))
        if not block:
            return 5  # PAM_BUF_ERR
        responses = C.cast(block, C.POINTER(Response))
        try:
            for index in range(count):
                style = messages[index].contents.style
                if style in credentials:
                    responses[index].text = libc.strdup(credentials[style])
                    if not responses[index].text:
                        raise MemoryError()
                elif style not in (3, 4):  # Error/info messages require no answer.
                    raise ValueError()
            output[0] = responses
            return 0
        except Exception:
            for index in range(count):
                libc.free(responses[index].text)
            libc.free(block)
            return 19

    conversation = PamConversation(converse, None)
    handle = C.c_void_p()
    result = lib.pam_start(b'helloboard', credentials[2], C.byref(conversation), C.byref(handle))
    if result != 0:
        if handle.value:
            lib.pam_end(handle, result)
        return False
    try:
        result = lib.pam_authenticate(handle, 0x8001)  # SILENT, DISALLOW_NULL_AUTHTOK
        if result == 0:
            result = lib.pam_acct_mgmt(handle, 0)
        return result == 0
    finally:
        lib.pam_end(handle, result)
