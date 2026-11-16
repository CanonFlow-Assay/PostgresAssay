"""Build a deterministic, self-contained offline zipapp; no package install needed."""
from pathlib import Path
import zipfile, hashlib
root=Path(__file__).resolve().parents[1]
out=root/'artifacts'/'postgres_assay.pyz'
out.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED) as archive:
    files={str(p.relative_to(root/'src')):p.read_bytes() for p in sorted((root/'src').rglob('*')) if p.is_file() and p.suffix in ('.py','.json')}
    files['__main__.py']=b'from postgres_assay.engine import main\nraise SystemExit(main("postgres_assay"))\n'
    for name,data in sorted(files.items()):
        info=zipfile.ZipInfo(name,date_time=(2026,11,16,0,0,0)); info.compress_type=zipfile.ZIP_DEFLATED
        archive.writestr(info,data)
print(out)
print(hashlib.sha256(out.read_bytes()).hexdigest())
