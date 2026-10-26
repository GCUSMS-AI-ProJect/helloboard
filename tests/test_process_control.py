"""Verify process identities, permissions and real signals using disposable children."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from process_control import ProcessManager
from wifi import create_app


def stat(name='worker', started=90, state='S', flags=0, parent=1):
    fields = [state] + ['0'] * 21
    fields[1], fields[6], fields[19] = str(parent), str(flags), str(started)
    return '123 (' + name + ') ' + ' '.join(fields)


class ProcessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.proc = Path(self.temp.name)
        (self.proc / '123').mkdir()
        (self.proc / '123/stat').write_text(stat())
        self.metrics = Mock()
        self.metrics.process_snapshot.return_value = [dict(pid=123, started=90, name='worker', state='S', flags=0, memory=8192, cpu_percent=1.2)]
        self.manager = ProcessManager(self.metrics, proc=self.proc)
        self.payload = dict(action='terminate', targets=[dict(pid=123, started=90)])

    def test_list_has_identity_and_never_contains_command_lines_or_credentials(self):
        data = self.manager.snapshot()
        self.assertTrue(data['items'][0]['selectable'])
        self.assertEqual(set(data['items'][0]), {'pid','started','name','memory','cpu_percent','selectable','reason'})

    def test_malformed_bulk_requests_are_rejected_before_any_signal(self):
        bad = [None, {}, {'action':'stop','targets':[]}, {'action':'kill','targets':[]},
               {'action':'kill','targets':[{'pid':True,'started':90}]},
               {'action':'kill','targets':[{'pid':-1,'started':90}]},
               {'action':'kill','targets':[{'pid':123,'started':'90'}]},
               {'action':'kill','targets':[{'pid':123,'started':90}]*2},
               {'action':'kill','targets':[{'pid':p,'started':90} for p in range(100,133)]}]
        with patch('process_control.os.pidfd_open') as opened:
            for payload in bad:
                with self.subTest(payload=payload), self.assertRaises(ValueError): self.manager.terminate(payload)
            opened.assert_not_called()

    def test_pid_reuse_is_rejected_and_handle_closed(self):
        (self.proc / '123/stat').write_text(stat(started=91))
        with patch('process_control.os.pidfd_open',return_value=71), patch('process_control.os.close') as close, patch('process_control.signal.pidfd_send_signal') as send:
            result=self.manager.terminate(self.payload)['results'][0]
            self.assertEqual(result['status'],'changed')
            send.assert_not_called(); close.assert_called_once_with(71)

    def test_correct_identity_signals_only_the_open_handle(self):
        for action, expected in [('terminate',signal.SIGTERM),('kill',signal.SIGKILL)]:
            with patch('process_control.os.pidfd_open',return_value=71) as opened, patch('process_control.os.close') as close, patch('process_control.signal.pidfd_send_signal') as send:
                result=self.manager.terminate(dict(self.payload,action=action))['results'][0]
                self.assertEqual(result['status'],'sent')
                opened.assert_called_once_with(123,0)
                send.assert_called_once_with(71,expected); close.assert_called_once_with(71)

    def test_critical_kernel_zombie_and_own_processes_cannot_be_signaled(self):
        cases=[stat(name='NetworkManager'),stat(flags=0x00200000),stat(state='Z'),stat(name='systemd')]
        with patch('process_control.os.pidfd_open',return_value=71), patch('process_control.os.close'), patch('process_control.signal.pidfd_send_signal') as send:
            for value in cases:
                (self.proc / '123/stat').write_text(value)
                self.assertEqual(self.manager.terminate(self.payload)['results'][0]['status'],'protected')
            send.assert_not_called()
        real=ProcessManager(self.metrics)
        own=real._read(os.getpid())
        result=real.terminate(dict(action='kill',targets=[dict(pid=os.getpid(),started=own['started'])]))
        self.assertEqual(result['results'][0]['status'],'protected')

    def test_partial_failures_are_per_process_without_unsafe_pid_fallback(self):
        payload=dict(action='terminate',targets=[dict(pid=123,started=90),dict(pid=124,started=90),dict(pid=125,started=90)])
        with patch('process_control.os.pidfd_open',side_effect=[ProcessLookupError(),PermissionError(),OSError()]), patch('process_control.signal.pidfd_send_signal') as send, patch('process_control.os.kill') as unsafe:
            results=self.manager.terminate(payload)['results']
            self.assertEqual([r['status'] for r in results],['exited','denied','unavailable'])
            send.assert_not_called(); unsafe.assert_not_called()

    def test_preview_unsupported_and_overlapping_operations_fail_closed(self):
        self.manager.preview=True
        with self.assertRaises(PermissionError): self.manager.terminate(self.payload)
        self.manager.preview=False
        with patch.object(self.manager,'supported',return_value=False), self.assertRaises(PermissionError): self.manager.terminate(self.payload)
        with self.manager.lock, self.assertRaises(Exception) as caught: self.manager.terminate(self.payload)
        self.assertEqual(type(caught.exception).__name__,'BusyError')

    @unittest.skipUnless(ProcessManager.supported(), 'Linux pidfd support required')
    def test_real_disposable_child_exits_and_other_child_keeps_running(self):
        children=[subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']) for _ in range(2)]
        try:
            manager=ProcessManager(self.metrics)
            child=manager._read(children[0].pid)
            result=manager.terminate(dict(action='terminate',targets=[dict(pid=children[0].pid,started=child['started'])]))
            self.assertEqual(result['results'][0]['status'],'sent')
            self.assertEqual(children[0].wait(timeout=3),-signal.SIGTERM)
            self.assertIsNone(children[1].poll())
        finally:
            for child in children:
                if child.poll() is None: child.terminate()
                child.wait(timeout=3)


class ProcessApiTests(unittest.TestCase):
    def setUp(self):
        self.auth=Mock(username='ubuntu')
        self.manager=Mock(preview=False)
        self.manager.snapshot.return_value={'items':[],'preview':False,'supported':True,'max_batch':32}
        self.manager.terminate.return_value={'results':[{'pid':123,'started':90,'status':'sent','message':'已发送退出请求'}]}
        self.app=create_app(object(),authenticator=self.auth,processes=self.manager)
        self.client=self.app.test_client()
        self.client.get('/system_status')
        with self.client.session_transaction() as session:
            self.headers={'X-CSRF-Token':session['csrf']}
            session['authorized_user']='ubuntu'
        self.payload=dict(action='terminate',targets=[dict(pid=123,started=90)],username='ubuntu',password='test-only')

    def test_fresh_credentials_required_even_with_existing_browser_grant(self):
        for _ in range(2):
            response=self.client.post('/api/processes/terminate',json=self.payload,headers=self.headers)
            self.assertEqual(response.status_code,200)
        self.assertEqual(self.auth.verify.call_count,2)
        self.assertEqual(self.manager.terminate.call_count,2)
        self.auth.verify.side_effect=PermissionError('wrong password')
        self.assertEqual(self.client.post('/api/processes/terminate',json=self.payload,headers=self.headers).status_code,403)
        self.assertEqual(self.manager.terminate.call_count,2)

    def test_bad_user_csrf_origin_and_preview_never_execute(self):
        for headers,payload in [({},self.payload),(dict(self.headers,Origin='http://elsewhere.local'),self.payload),(self.headers,dict(self.payload,username='root'))]:
            self.assertEqual(self.client.post('/api/processes/terminate',json=payload,headers=headers).status_code,403)
        self.manager.preview=True
        self.assertEqual(self.client.post('/api/processes/terminate',json=self.payload,headers=self.headers).status_code,403)
        self.manager.terminate.assert_not_called(); self.auth.verify.assert_not_called()

    def test_process_reads_have_no_mutations_and_public_hosts_rejected(self):
        response=self.client.get('/api/processes')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.headers['Cache-Control'],'no-store')
        self.manager.terminate.assert_not_called(); self.auth.verify.assert_not_called()
        self.assertEqual(self.client.get('/api/processes',headers={'Host':'public.example.com'}).status_code,403)

    @unittest.skipUnless(ProcessManager.supported(), 'Linux pidfd support required')
    def test_authenticated_http_action_ends_only_its_disposable_child(self):
        child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])
        try:
            manager=ProcessManager(Mock())
            started=manager._read(child.pid)['started']
            app=create_app(object(),authenticator=self.auth,processes=manager)
            client=app.test_client()
            client.get('/system_status')
            with client.session_transaction() as session:
                headers={'X-CSRF-Token':session['csrf']}
            response=client.post('/api/processes/terminate',json=dict(self.payload,
                targets=[dict(pid=child.pid,started=started)]),headers=headers)
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.json['results'][0]['status'],'sent')
            self.assertEqual(child.wait(timeout=3),-signal.SIGTERM)
            self.auth.verify.assert_called_once_with('test-only')
        finally:
            if child.poll() is None: child.terminate()
            child.wait(timeout=3)


if __name__=='__main__': unittest.main()
