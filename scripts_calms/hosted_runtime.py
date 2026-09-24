"""Budgeted hosted Linux transport. All commands and raw responses are retained."""
import hashlib
import json
import os
import sqlite3
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from calms.common import canonical, digest, load_env, write_json


class HostedRuntime:
    def __init__(self, root, output, memory='4g'):
        self.root=Path(root); self.output=Path(output); self.output.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(self.root/'calms_runs/api_ledger.sqlite',timeout=30)
        self.sequence=0; self.started=time.monotonic()
        if (self.output/'container.response.json').exists():
            raise RuntimeError('Prior container attempt exists: inspect it instead of silently repeating')
        key=self.reserve('container', {'memory':memory}, {'1g':.03,'4g':.12,'16g':.48}[memory])
        load_env(self.root/'.env')
        self.container=self.request('container','POST','containers',{'name':'calms-appworld','memory_limit':memory,
                        'expires_after':{'anchor':'last_active_at','minutes':20}})['id']
        self.settle(key,{'cost_usd':{'1g':.03,'4g':.12,'16g':.48}[memory],'infrastructure':True})

    def reserve(self,name,body,amount):
        key=digest({'operation':name,'output':str(self.output.resolve()),'body':body})
        self.db.execute('BEGIN IMMEDIATE')
        if self.db.execute('select 1 from calls where key=?',(key,)).fetchone():
            self.db.rollback(); raise RuntimeError('Ambiguous repeated paid operation blocked')
        if self.db.execute('select coalesce(sum(cost),0) from calls').fetchone()[0]+amount>95:
            self.db.rollback(); raise RuntimeError('Cumulative spending cap reached')
        self.db.execute("insert into calls values (?,'pending',?,?,NULL)",(key,amount,amount)); self.db.commit()
        return key

    def settle(self,key,receipt):
        self.db.execute("update calls set status='done',cost=?,response=? where key=?",
                        (receipt['cost_usd'],canonical(receipt),key)); self.db.commit()

    def request(self,name,method,path,payload=None,upload=None,binary=False):
        headers={'Authorization':'Bearer '+os.environ['OPENAI_API_KEY']}
        if upload:
            boundary='calms'+uuid.uuid4().hex
            data=(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{upload.name}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode()
                  +upload.read_bytes()+f'\r\n--{boundary}--\r\n'.encode())
            headers['Content-Type']='multipart/form-data; boundary='+boundary
        else:
            data=canonical(payload).encode() if payload is not None else None
            headers['Content-Type']='application/json'
        write_json(self.output/f'{name}.request.json',{'method':method,'path':path,'body':payload,
                   'upload_sha256':hashlib.sha256(upload.read_bytes()).hexdigest() if upload else None})
        req=urllib.request.Request('https://api.openai.com/v1/'+path,data=data,headers=headers,method=method)
        try:
            with urllib.request.urlopen(req,timeout=1200) as response: raw=response.read()
        except urllib.error.HTTPError as e:
            (self.output/f'{name}.error.json').write_bytes(e.read())
            raise RuntimeError(f'Hosted HTTP {e.code}; error body retained') from None
        (self.output/f'{name}.response.{"bin" if binary else "json"}').write_bytes(raw)
        return raw if binary else json.loads(raw)

    def upload(self,path):
        self.sequence+=1
        return self.request(f'upload-{self.sequence}','POST','containers/'+self.container+'/files',upload=Path(path))['path']

    def shell(self,command):
        # End sessions well within one conservatively charged 20-minute block.
        if time.monotonic()-self.started>900: raise RuntimeError('Session age limit reached; save artifacts and start a new session')
        self.sequence+=1; name=f'shell-{self.sequence}'
        key=self.reserve(name,{'command':command},.10)
        response=self.request(name,'POST','responses',{'model':'gpt-6-sol','store':False,'reasoning':{'effort':'low'},
            'max_output_tokens':2048,'tool_choice':'required',
            'tools':[{'type':'shell','environment':{'type':'container_reference','container_id':self.container}}],
            'input':'Execute exactly this one command once with timeout_ms 600000. Do not modify it, run additional commands, retry failures, inspect files, or infer output. Stop after tool output.\n'+command})
        usage=response['usage']; cached=usage.get('input_tokens_details',{}).get('cached_tokens',0)
        cost=((usage['input_tokens']-cached)*2+cached*.2+usage['output_tokens']*10)/1e6
        self.settle(key,{'cost_usd':cost,'infrastructure':True,'usage':usage,'response_id':response['id']})
        calls=[i for i in response.get('output',[]) if i['type']=='shell_call']
        if len(calls)!=1 or calls[0]['action']['commands']!=[command]: raise RuntimeError('Unexpected hosted command')
        outputs=[o for i in response['output'] if i['type']=='shell_call_output' for o in i['output']]
        if len(outputs)!=1: raise RuntimeError('Missing native shell output')
        return outputs[0]

    def download(self,path,destination):
        self.sequence+=1
        file=None
        for poll in range(180):
            if poll and poll % 6 == 0:
                import shlex
                code='from pathlib import Path; print("READY" if Path('+repr(path)+').exists() else "WAIT")'
                self.shell('python -c '+shlex.quote(code))
            listing=self.request(f'files-{self.sequence}-{poll}','GET','containers/'+self.container+'/files?limit=100')
            file=next((f for f in listing['data'] if f['path']==path),None)
            page=0
            while not file and listing.get('has_more'):
                page+=1
                listing=self.request(f'files-{self.sequence}-{poll}-page{page}','GET',
                       'containers/'+self.container+'/files?limit=100&after='+listing['last_id'])
                file=next((f for f in listing['data'] if f['path']==path),None)
            if file: break
            time.sleep(5)
        if not file: raise RuntimeError('No completed artifact within 15 minutes')
        raw=self.request(f'download-{self.sequence}','GET','containers/'+self.container+'/files/'+file['id']+'/content',binary=True)
        Path(destination).write_bytes(raw)
        return raw

    def close(self):
        try: self.request('cleanup','DELETE','containers/'+self.container)
        finally: self.db.close()
