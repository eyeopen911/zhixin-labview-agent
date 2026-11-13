#!/usr/bin/env python3
from http.server import ThreadingHTTPServer
import os,threading,webbrowser
from backend import AppState,build_handler
from dispatcher import dispatch
from settings import remote_enabled
if __name__=='__main__':
    state=AppState(executor=dispatch if remote_enabled() else None)
    server=ThreadingHTTPServer(('127.0.0.1',8766),build_handler(state))
    print('执信 NI 助手 http://127.0.0.1:8766 · Codex CLI · natural-language VI design / verified NI execution',flush=True)
    if os.environ.get('NI_AGENT_OPEN_BROWSER')=='1':threading.Timer(0.5,lambda:webbrowser.open('http://127.0.0.1:8766')).start()
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
