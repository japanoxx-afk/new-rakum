"""Read-only sampling of known RhakMu 1.000d command/lockstep counters.

No injection, breakpoints, memory writes, keyboard monitoring or packet payloads.
Packet index changes mean batch construction, NOT a proven on-wire timestamp.
Sampling may miss commands queued and removed between observations.
"""
import argparse
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import statistics
import struct
import time
import viewport_patch

def decode(manager, frame, local):
    if local not in range(8):raise ValueError('Local player slot out of range')
    fields=lambda offset,fmt:struct.unpack_from(fmt,manager,offset)
    base=0x50+local*0x284
    return dict(frame=frame,local_player=local,queue_head=fields(4,'<I')[0],
        batch_sequence=fields(0x38,'<I')[0],latency_turns=fields(0x48,'<h')[0],
        player_counters=fields(base+0x10,'<2h'),
        player_sequence_counters=fields(base+0x1c,'<2I'))

def summarize(samples):
    intervals=[];last=None
    for row in samples:
        if last is None or row['batch_sequence']!=last['batch_sequence']:
            if last is not None:
                delta=(row['batch_sequence']-last['batch_sequence']) & 0xffffffff
                if delta==1:intervals.append(row['ms']-last['ms'])
            last=row
    return dict(samples=len(samples),batch_interval_median_ms=statistics.median(intervals) if intervals else None,
        batch_interval_min_ms=min(intervals) if intervals else None,
        batch_interval_max_ms=max(intervals) if intervals else None,
        latency_values=sorted({r['latency_turns'] for r in samples}),
        warning='Batch construction intervals only; not click-to-action or on-wire latency.')

def capture(pid,seconds):
    api=ctypes.WinDLL('kernel32',use_last_error=True)
    api.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    api.OpenProcess.restype=wintypes.HANDLE
    api.CloseHandle.argtypes=[wintypes.HANDLE]
    api.QueryFullProcessImageNameW.argtypes=[wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)]
    api.ReadProcessMemory.argtypes=[wintypes.HANDLE,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t,ctypes.POINTER(ctypes.c_size_t)]
    handle=api.OpenProcess(0x1010,False,pid)
    if not handle:raise ctypes.WinError(ctypes.get_last_error())
    def read(address,size):
        if address<0x10000 or address+size>0x80000000:raise ValueError('Invalid 32-bit pointer')
        buffer=ctypes.create_string_buffer(size);count=ctypes.c_size_t()
        if not api.ReadProcessMemory(handle,address,buffer,size,ctypes.byref(count)) or count.value!=size:
            raise ctypes.WinError(ctypes.get_last_error())
        return buffer.raw
    try:
        name=ctypes.create_unicode_buffer(32768);n=wintypes.DWORD(len(name))
        if not api.QueryFullProcessImageNameW(handle,0,name,ctypes.byref(n)):raise ctypes.WinError(ctypes.get_last_error())
        exe=Path(name.value)
        if exe.name.lower()!='rhakmu.exe':raise ValueError('Select only Rhakmu.exe')
        viewport_patch.transform(exe.read_bytes(),False) # known whole-file validation
        samples=[];start=time.perf_counter();last_key=None;misses=0
        while time.perf_counter()-start<seconds:
            try:
                pointer=struct.unpack('<I',read(0xb411a4,4))[0]
                frame=struct.unpack('<I',read(0xb412b4,4))[0]
                local=struct.unpack('<b',read(0xb412cc,1))[0]
                manager=read(pointer,0x1470)
                if struct.unpack('<I',read(0xb411a4,4))[0]!=pointer:raise ValueError('Scene transition')
                row=decode(manager,frame,local)
                head=row.pop('queue_head')
                row['command_pending']=bool(head)
                if head:
                    # Export only the queued event's ordering stamp, not payload.
                    row['queued_order_stamp']=struct.unpack('<I',read(head,4))[0]
                key=tuple((k,repr(v)) for k,v in row.items())
                if key!=last_key:
                    row['ms']=round((time.perf_counter()-start)*1000,3)
                    samples.append(row);last_key=key
            except (OSError,ValueError):misses+=1
            time.sleep(0.005)
        return dict(schema=1,read_only=True,pid=pid,seconds=seconds,misses=misses,
                    summary=summarize(samples),samples=samples)
    finally:api.CloseHandle(handle)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pid',type=int);parser.add_argument('--seconds',type=float,default=20)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if not 1<=args.seconds<=60:parser.error('seconds must be 1..60')
    result=capture(args.pid,args.seconds)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2)
    print(json.dumps(result['summary'],indent=2))
