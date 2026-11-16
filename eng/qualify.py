"""Retain local qualification and a producer-bound native-evidence assessment."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
PACKAGE=next(p.name for p in (ROOT/'src').iterdir() if p.is_dir())


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--native',action='store_true');args=parser.parse_args()
    out=ROOT/'artifacts';out.mkdir(exist_ok=True)
    runs=[]
    def execute(name,argv,expected=(0,)):
        proc=subprocess.run(argv,cwd=ROOT,capture_output=True,text=True,timeout=240)
        log=(proc.stdout+proc.stderr).encode();(out/(name+'.log')).write_bytes(log)
        runs.append({'name':name,'argv':[Path(v).name if v==sys.executable else v for v in argv], 'exitCode':proc.returncode,'expectedExitCodes':list(expected),'logSha256':hashlib.sha256(log).hexdigest(),'passed':proc.returncode in expected})
        if proc.returncode not in expected:print(proc.stdout+proc.stderr)
        return proc
    execute('unit',[sys.executable,'-m','unittest','discover','-s','tests','-v'])
    execute('package',[sys.executable,'eng/package.py'])
    native=None
    if args.native:
        run=execute('native',[sys.executable,'eng/native_smoke.py'])
        if run.returncode==0:
            native=json.loads((out/'native-results.json').read_text())
            snapshot=out/'native-snapshot.json'
            native['snapshotSha256']=hashlib.sha256(snapshot.read_bytes()).hexdigest()
            (out/'native-results.json').write_text(json.dumps(native,indent=2)+'\n')
            (out/'accept_native.py').write_text('''import hashlib,json
from pathlib import Path
result=json.loads(Path('native-results.json').read_text())
assert result['status']=='Pass'
assert hashlib.sha256(Path('native-snapshot.json').read_bytes()).hexdigest()==result['snapshotSha256']
''')
            catalog=json.loads((ROOT/'src'/PACKAGE/'catalogue.json').read_text())
            policy={'schemaVersion':1,'profile':catalog['profiles'][0], 'requiredCommands':[[sys.executable,'accept_native.py']],'inputs':['native-results.json','accept_native.py']}
            (out/'native-policy.json').write_text(json.dumps(policy,indent=2)+'\n')
            archive=out/(PACKAGE+'.pyz')
            expected=0 if catalog['product']=='duckdb' else 1
            execute('native-assessment',[sys.executable,str(archive),'verify',str(snapshot),'--policy',str(out/'native-policy.json'),'--out',str(out/'native-receipt.json')],(expected,))
    files={}
    for folder in ['src','tests','eng']:
        for p in sorted((ROOT/folder).rglob('*')):
            if p.is_file() and p.suffix in ('.py','.json'):
                files[str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest()
    report={'schemaVersion':1,'status':'Pass' if all(r['passed'] for r in runs) else 'Fail','python':sys.version.split()[0], 'commands':runs,'native':native,'sourceFiles':files,'scope':'Local unit/qualification cases and optional disposable native engine; not production deployment certification.'}
    (out/'qualification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'nativeIncluded':args.native,'runs':[{k:r[k] for k in ['name','exitCode','passed']} for r in runs]},indent=2))
    return 0 if report['status']=='Pass' else 1


if __name__=='__main__':raise SystemExit(main())
