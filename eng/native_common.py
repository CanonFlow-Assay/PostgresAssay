"""Disposable Docker lifecycle. Only containers created here are removed."""
from contextlib import contextmanager
import json
import subprocess
import time
import uuid


def call(argv, data=None, timeout=60):
    result=subprocess.run(argv,input=data,capture_output=True,text=True,timeout=timeout)
    if result.returncode:
        raise RuntimeError('command failed: '+argv[0]+' '+result.stderr[-1200:])
    return result.stdout


@contextmanager
def container(image,extra):
    name='canonflow-assay-'+uuid.uuid4().hex[:12]
    identity=call(['docker','image','inspect',image,'--format','{{json .RepoDigests}}']).strip()
    created=False
    try:
        call(['docker','run','--detach','--name',name,'--network','none','--memory','2g','--cpus','2',*extra,image])
        created=True
        yield name,json.loads(identity)
    finally:
        if created:call(['docker','rm','--force','--volumes',name])


def ready(probe,seconds=90):
    deadline=time.monotonic()+seconds
    last=None
    while time.monotonic()<deadline:
        try:return probe()
        except (RuntimeError,ValueError) as error:last=error
        time.sleep(.5)
    raise RuntimeError('disposable engine did not become ready') from last
