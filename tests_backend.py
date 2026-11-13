import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
import threading
import unittest
import urllib.error
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import patch
import backend

class Plans(unittest.TestCase):
    def test_chinese_offset(self):
        plan=backend.make_plan('生成偏置校正 VI',{'RawCurrent':15,'Offset':2.5})
        self.assertEqual(plan['expected_result'],12.5)
        self.assertFalse(plan['execution_available'])
    def test_scale(self):
        self.assertEqual(backend.make_plan('scale current')['expected_result'],6.25)
    def test_numeric_validation(self):
        for bad in (float('nan'),float('inf'),True,'1'):
            with self.assertRaises(backend.APIError):backend.make_plan('offset',{'RawCurrent':bad})
    def test_no_command_dispatch(self):
        with self.assertRaises(backend.APIError):backend.make_plan('run arbitrary shell command')
        with self.assertRaises(backend.APIError):backend.make_plan('scale',{'command':'cmd.exe'})
    def test_reject_invalid_shapes(self):
        with self.assertRaises(backend.APIError):backend.make_plan('offset',[])
        with self.assertRaises(backend.APIError):backend.AppState().enqueue([])
    def test_job_without_executor_does_not_execute(self):
        state=backend.AppState(backend.ModelConfig())
        job=state.enqueue('offset_correction')
        self.assertEqual(job['status'],'awaiting_executor')
        self.assertFalse(job['executed'])
    def test_provider_failure_hides_key(self):
        cfg=backend.ModelConfig('SECRET-EXAMPLE','https://example.invalid/v1','demo')
        with patch('urllib.request.urlopen',side_effect=ValueError('SECRET-EXAMPLE')):
            with self.assertRaises(backend.APIError) as error:backend.model_chat(cfg,'hello')
        self.assertNotIn(cfg.api_key,error.exception.message)
    def test_config_rejects_embedded_credentials(self):
        with self.assertRaises(backend.APIError):backend.ModelConfig('k','https://user:pass@example.com/v1','m').endpoint()

class Codex(unittest.TestCase):
    def test_cli_runs_empty_readonly_directory_and_returns_final_only(self):
        def run(command, **kwargs):
            self.assertIn('--ephemeral', command)
            self.assertEqual(command[command.index('--sandbox')+1], 'read-only')
            self.assertIn('mcp_servers={}', command)
            self.assertIn('features.shell_tool=false', command)
            self.assertNotIn('--dangerously-bypass-approvals-and-sandbox', command)
            self.assertEqual(list(Path(kwargs['cwd']).iterdir()), [])
            self.assertIn('Do not use tools', kwargs['input'])
            self.assertFalse(kwargs.get('shell', False))
            output=Path(command[command.index('--output-last-message')+1])
            output.write_text('仅是计划，未执行。')
            return SimpleNamespace(returncode=0)
        with patch('backend.subprocess.run', side_effect=run):
            result=backend.codex_chat('帮我生成一个偏置校正 VI', '/fake/codex')
        self.assertEqual(result['reply'],'仅是计划，未执行。')
        self.assertFalse(result['executed'])
    def test_cli_timeout_hides_internal_text(self):
        with patch('backend.subprocess.run',side_effect=subprocess.TimeoutExpired('SECRET-EXAMPLE',120)):
            with self.assertRaises(backend.APIError) as error:backend.codex_chat('hello','/fake/codex')
        self.assertEqual(error.exception.code,'CODEX_TIMEOUT')
        self.assertNotIn('SECRET-EXAMPLE',error.exception.message)
    def test_cli_failure_does_not_expose_stderr(self):
        with patch('backend.subprocess.run',return_value=SimpleNamespace(returncode=1,stderr='SECRET-EXAMPLE')):
            with self.assertRaises(backend.APIError) as error:backend.codex_chat('hello','/fake/codex')
        self.assertNotIn('SECRET-EXAMPLE',error.exception.message)
    def test_cli_missing(self):
        with patch('backend.find_codex_cli',return_value=None):
            with self.assertRaises(backend.APIError) as error:backend.codex_chat('hello')
        self.assertEqual(error.exception.code,'CODEX_NOT_INSTALLED')
    def test_health_distinguishes_installed_and_login(self):
        with patch('backend.find_codex_cli',return_value='/fake/codex'):
            state=backend.AppState(provider='codex')
            self.assertTrue(state.provider_status()['installed'])
            self.assertEqual(state.provider_status()['login_status'],'not_verified')
    def test_success_updates_provider_status(self):
        state=backend.AppState(provider='codex')
        with patch('backend.codex_chat',return_value={'reply':'yes','executed':False}):state.chat('hi')
        self.assertEqual(state.provider_status()['login_status'],'verified_by_successful_request')
    def test_cli_output_key_redaction(self):
        def run(command, **kwargs):
            Path(command[command.index('--output-last-message')+1]).write_text('SECRET-EXAMPLE')
            return SimpleNamespace(returncode=0)
        with patch.dict(os.environ,{'NI_AGENT_API_KEY':'SECRET-EXAMPLE'}),patch('backend.subprocess.run',side_effect=run):
            self.assertEqual(backend.codex_chat('hi','/fake/codex')['reply'],'[REDACTED]')


class HTTP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state=backend.AppState(backend.ModelConfig())
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),backend.build_handler(cls.state))
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join()
    def request(self,method,path,obj=None,token=True,origin=None,raw=None):
        c=HTTPConnection('127.0.0.1',self.server.server_port)
        headers={}
        if token:headers['X-NI-Agent-Token']=self.state.token
        if origin:headers['Origin']=origin
        data=raw if raw is not None else json.dumps(obj).encode() if obj is not None else None
        if data is not None:headers['Content-Type']='application/json'
        c.request(method,path,data,headers);r=c.getresponse();status=r.status;body=json.loads(r.read());c.close();return status,body
    def test_health(self):
        status,body=self.request('GET','/api/health')
        self.assertEqual(status,200);self.assertFalse(body['model_configured'])
        self.assertNotIn('api_key',body)
    def test_token(self):
        self.assertEqual(self.request('POST','/api/plan',{'prompt':'offset'},token=False)[0],403)
    def test_cross_origin_even_with_token(self):
        self.assertEqual(self.request('POST','/api/plan',{'prompt':'offset'},origin='https://evil.invalid')[0],403)
    def test_plan(self):
        self.assertEqual(self.request('POST','/api/plan',{'prompt':'TestStand 示例'})[1]['task'],'teststand_demo')
    def test_chat_disabled(self):
        status,body=self.request('POST','/api/chat',{'message':'hi'})
        self.assertEqual(status,503);self.assertEqual(body['error']['code'],'MODEL_NOT_CONFIGURED')
    def test_job_rejects_target_injection(self):
        self.assertEqual(self.request('POST','/api/jobs',{'task':'offset_correction','confirm':True,'target':'production'})[0],400)
    def test_body_limit(self):
        self.assertEqual(self.request('POST','/api/plan',raw=b'x'*65537)[0],413)
    def test_malformed_json(self):
        self.assertEqual(self.request('POST','/api/plan',raw=b'{')[0],400)
    def test_jobs(self):
        status,job=self.request('POST','/api/jobs',{'task':'scale_current','confirm':True})
        self.assertEqual(status,202);self.assertFalse(job['executed'])
        self.assertEqual(self.request('GET','/api/jobs')[0],200)

if __name__=='__main__':unittest.main()
