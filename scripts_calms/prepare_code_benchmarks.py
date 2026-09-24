"""Download official expanded tests and freeze splits; never execute dataset code."""
import gzip
import hashlib
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from calms.common import digest, write_json, write_jsonl


def main():
    target = ROOT/'calms_data/code-20260923'
    target.mkdir(parents=True, exist_ok=True)
    sources, tasks, splits = [], [], {}
    for name, version, test_count in [('HumanEvalPlus','v0.1.10',80),('MbppPlus','v0.2.0',120)]:
        url = f'https://github.com/evalplus/{name.lower()}_release/releases/download/{version}/{name}.jsonl.gz'
        archive = target/f'{name}-{version}.jsonl.gz'
        if not archive.exists():
            request = urllib.request.Request(url, headers={'User-Agent':'CALM-S-research'})
            with urllib.request.urlopen(request, timeout=180) as response:
                data = response.read()
            gzip.decompress(data)  # Reject an HTML/error response before saving.
            archive.write_bytes(data)
        raw = archive.read_bytes()
        rows = [json.loads(line) for line in gzip.decompress(raw).decode().splitlines() if line.strip()]
        rows.sort(key=lambda r: digest(['calms-code-split-20260923',r['task_id']]))
        assert len({r['task_id'] for r in rows}) == len(rows)
        ids = {'dev':[r['task_id'] for r in rows[:40]],
               'test':[r['task_id'] for r in rows[40:40+test_count]],
               'unused':[r['task_id'] for r in rows[40+test_count:]]}
        splits[name] = ids
        for split in ('dev','test'):
            selected = [r for r in rows if r['task_id'] in ids[split]]
            write_jsonl(target/f'{name}-{split}-private.jsonl',selected)
            for r in selected:
                tasks.append({'id':r['task_id'],'family':name,'split':split,
                    'instruction':'Return a complete Python solution, including the function definition and required imports.\n'+r['prompt']})
        sources.append({'benchmark':name,'version':version,'url':url,'tasks':len(rows),
                        'sha256':hashlib.sha256(raw).hexdigest()})
    assert len({r['id'] for r in tasks}) == len(tasks)
    write_jsonl(target/'public-prompts.jsonl',tasks)
    write_json(target/'splits.json',splits)
    revisions = {}
    for repo in ('evalplus','appworld'):
        revisions[repo] = subprocess.check_output(['git','-C',str(ROOT/'calms_data/external-sources'/repo),
            'rev-parse','HEAD'],text=True).strip()
    write_json(target/'dataset-manifest.json',{'sources':sources,'revisions':revisions,
        'selection':'Deterministic hash ordering fixed before model collection; 40 dev per benchmark, 80 HumanEval+ test and 120 MBPP+ test.',
        'api_calls':0,'generated_code_executed':False,'public_prompts_sha256':digest(tasks),
        'status':'DATA PREPARED ONLY. Official expanded-test Docker adapter still requires integration and runtime validation.',
        'limitations':'Public benchmark contamination possible; disjoint task IDs do not prove semantic deduplication.'})
    print(json.dumps({'tasks':len(tasks),'dev':80,'test':200,'sources':sources,'revisions':revisions}))


if __name__ == '__main__':
    main()
