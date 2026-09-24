"""Bounded OpenAI hosted-shell availability probe, recorded in the shared ledger."""
import argparse
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from calms.common import canonical,digest,load_env,write_json


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--live',action='store_true')
    args=parser.parse_args()
    if not args.live:
        raise SystemExit('No keys read. Hosted sandbox probe requires --live.')
    out=ROOT/'calms_runs/hosted-sandbox-probe-20260924'
    out.mkdir(parents=True,exist_ok=True)
    spec={'operation':'hosted-shell-probe','model':'gpt-6-sol','memory_limit':'1g','max_output_tokens':1536}
    key=digest(spec)
    db=sqlite3.connect(ROOT/'calms_runs/api_ledger.sqlite',timeout=30)
    db.execute('BEGIN IMMEDIATE')
    if db.execute('select 1 from calls where key=?',(key,)).fetchone():
        db.rollback()
        raise SystemExit('Probe already recorded; inspect its retained result instead of repeating a paid request.')
    if db.execute('select coalesce(sum(cost),0) from calls').fetchone()[0]+.5>95:
        db.rollback()
        raise SystemExit('Budget cap would be exceeded')
    db.execute("insert into calls values (?,'pending',.5,.5,NULL)",(key,))
    db.commit()
    load_env(ROOT/'.env')
    def request(name,method,path,payload=None):
        write_json(out/f'{name}.request.json',{'method':method,'path':path,'body':payload})
        data=canonical(payload).encode() if payload is not None else None
        req=urllib.request.Request('https://api.openai.com/v1/'+path,data=data,method=method,
            headers={'Authorization':'Bearer '+os.environ['OPENAI_API_KEY'],'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req,timeout=180) as response:
                raw=response.read()
        except urllib.error.HTTPError as error:
            raw=error.read()
            (out/f'{name}.http-error.json').write_bytes(raw)
            raise RuntimeError(f'HTTP {error.code}; retained server details in {out.name}') from None
        (out/f'{name}.response.json').write_bytes(raw)
        return json.loads(raw)
    container=None
    try:
        container=request('container','POST','containers',{'name':'calms-runtime-probe',
            'memory_limit':'1g','expires_after':{'anchor':'last_active_at','minutes':20}})
        command="python -c \"import sys,platform,importlib.util,json; print(json.dumps({'python':sys.version,'platform':platform.platform(),'libraries':{m:bool(importlib.util.find_spec(m)) for m in ['numpy','psutil','datasets','pip','appworld']}}))\""
        response=request('shell','POST','responses',{'model':'gpt-6-sol','store':False,
            'reasoning':{'effort':'low'},'max_output_tokens':1536,'tool_choice':'required',
            'tools':[{'type':'shell','environment':{'type':'container_reference','container_id':container['id']}}],
            'input':'Run exactly this single diagnostic shell command. Do not install packages or modify files. Do not substitute an inferred answer. After its output, stop. Command:\n'+command})
        usage=response['usage']
        cached=usage.get('input_tokens_details',{}).get('cached_tokens',0)
        token_cost=((usage['input_tokens']-cached)*2+cached*.2+usage['output_tokens']*10)/1e6
        result={'request_sha256':key,'text':'Hosted shell capability probe; see raw response artifacts.',
            'cost_usd':token_cost+.03,'token_cost_usd':token_cost,'container_cost_reserve_usd':.03,
            'cost_note':'Standard GPT-6 Sol rates and conservative full 20-minute 1GB container fee; provider billing authoritative.',
            'response_id':response['id'],'complete':response.get('status')=='completed','probe':True,
            'input_tokens':usage['input_tokens'],'output_tokens':usage['output_tokens'],'cached_tokens':cached}
        db.execute("update calls set status='done',cost=?,response=? where key=?",(result['cost_usd'],canonical(result),key))
        db.commit()
        write_json(out/'result.json',result)
        print(json.dumps({'probe_cost_usd':result['cost_usd'],'output':response.get('output',[])}))
    finally:
        if container:
            try:
                request('cleanup','DELETE','containers/'+container['id'])
            except Exception as error:
                write_json(out/'cleanup-error.json',{'type':type(error).__name__,'note':'Container expires automatically after inactivity.'})
        db.close()


if __name__=='__main__':
    main()
