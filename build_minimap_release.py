"""Generate exact release edits offline; runtime has no assembler dependency."""
import base64,json,zlib
from pathlib import Path
import minimap_preview_v5 as trial
import viewport_patch

def generate(source):
    variants=[]
    for high in (False,True):
        baseline=viewport_patch.transform(source,high)
        result=trial.build(baseline)
        edits=[];i=0
        while i<len(baseline):
            if baseline[i]==result[i]:i+=1;continue
            start=i
            while i<len(baseline) and baseline[i]!=result[i]:i+=1
            edits.append({'offset':start,'before':baseline[start:i].hex(),'after':result[start:i].hex()})
        variants.append({'highres':high,'edits':edits,'tail':base64.b64encode(zlib.compress(result[len(baseline):],9)).decode()})
    return {'version':1,'source_size':len(source),'patched_size':len(result),'variants':variants}

if __name__=='__main__':
    import sys
    spec=generate(Path(sys.argv[1]).read_bytes())
    print(json.dumps(spec,indent=2))
