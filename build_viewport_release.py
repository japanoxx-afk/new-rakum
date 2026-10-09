"""Generate data-only viewport patch instructions for the frozen launcher."""
import hashlib
import json
from pathlib import Path
from viewport_probe import transform,SOURCE_HASHES

def build(source,destination):
    patched,edits=transform(Path(source).read_bytes())
    previous=json.loads(Path(destination).read_text(encoding='utf-8')) if Path(destination).exists() else {}
    legacy=previous.get('legacy_edits',[])
    if previous.get('version') in (6,7,8,9):legacy=[previous['edits'],*legacy]
    payload=dict(schema=1,version=10,legacy_edits=legacy,source_hash=SOURCE_HASHES['Rhakmu.exe'],
                 dll_hashes={k:v for k,v in SOURCE_HASHES.items() if k!='Rhakmu.exe'},edits=edits)
    Path(destination).write_text(json.dumps(payload,indent=2),encoding='utf-8')
    return hashlib.sha256(patched).hexdigest()

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('source');parser.add_argument('destination')
    args=parser.parse_args();print(build(args.source,args.destination))
