"""Read local game JTL terrain pixels; no bundled proprietary assets."""
from pathlib import Path
import struct
from PIL import Image
from stb_tool import _iter_idx

DATA=Path(r'C:\Program Files (x86)\TriggerSoft\RhakMu\Data')
NAMES=('EAST','WEST','SAVAGE','DUNGEON')


def read_asset(name,data_dir=DATA):
    archive=data_dir/'Data000.FDB'
    offsets=set(off for off,path in _iter_idx((data_dir/'Data000.IDX').read_bytes(),archive.stat().st_size) if path.upper()==name.upper())
    if len(offsets)!=1:raise ValueError(f'리소스 위치 확인 실패: {name}')
    with archive.open('rb') as source:
        source.seek(offsets.pop());size=struct.unpack('<I',source.read(4))[0]
        if not 0<size<=64*1024*1024:raise ValueError('잘못된 리소스 크기')
        result=source.read(size)
    if len(result)!=size:raise ValueError('잘린 리소스')
    return result


def sprites565(data):
    """iCARUS RLE image set: 14-byte frame header, word-indexed rows."""
    groups=struct.unpack_from('<H',data,16)[0]
    if groups>4096:raise ValueError('잘못된 이미지 그룹 수')
    count=sum(struct.unpack_from(f'<{groups}H',data,18))
    pos=struct.unpack_from('<I',data,4)[0]
    frames=[]
    for _ in range(count):
        _,left,_,top,_,w,h=struct.unpack_from('<7h',data,pos);pos+=14
        if not (0<w<=2048 and 0<h<=2048):raise ValueError('잘못된 스프라이트 크기')
        rows=struct.unpack_from(f'<{h}I',data,pos);pos+=h*4
        size=struct.unpack_from('<I',data,pos)[0];pos+=4
        blob=data[pos:pos+size];pos+=size
        rgba=bytearray(w*h*4)
        for y,offset in enumerate(rows):
            p=offset*2;x=0
            while True:
                skip,run=struct.unpack_from('<HH',blob,p);p+=4
                if not skip and not run:break
                x+=skip
                if x+run>w:raise ValueError('스프라이트 행 범위 초과')
                for value in struct.unpack_from(f'<{run}H',blob,p):
                    at=(y*w+x)*4
                    rgba[at:at+4]=bytes((((value>>11)&31)*255//31,((value>>5)&63)*255//63,(value&31)*255//31,255));x+=1
                p+=run*2
        frames.append((Image.frombytes('RGBA',(w,h),bytes(rgba)),left,top))
    return frames


class TerrainTextures:
    def __init__(self, theme, data_dir=DATA):
        if theme not in range(4):raise ValueError('지원하지 않는 지형 테마')
        wanted=f'DATA\\TILE\\{NAMES[theme]}.JTL'
        archive=data_dir/'Data000.FDB'
        index=(data_dir/'Data000.IDX').read_bytes()
        offsets=set(off for off,name in _iter_idx(index,archive.stat().st_size) if name.upper()==wanted)
        if len(offsets)!=1:raise ValueError('타일 아카이브 위치를 확인할 수 없습니다.')
        with archive.open('rb') as source:
            source.seek(offsets.pop())
            size=struct.unpack('<I',source.read(4))[0]
            if not 18582<=size<=64*1024*1024:raise ValueError('잘못된 JTL 크기')
            self.data=source.read(size)
        self.count,self.pixels=struct.unpack_from('<HI',self.data,16)
        self.offset=struct.unpack_from('<I',self.data,4)[0] # RGB565 (format 1)
        if self.pixels!=16384 or self.offset+self.count*(16+self.pixels*2)>len(self.data):
            raise ValueError('지원하지 않는 JTL 배치')
        self.cache={}
        self.resources=ResourceTextures(theme,data_dir)

    def tile(self,index):
        if index in self.cache:return self.cache[index]
        if not 0<=index<self.count:raise ValueError(f'잘못된 타일 ID: {index}')
        offset=self.offset+index*(16+self.pixels*2)+16
        packed=struct.unpack_from(f'<{self.pixels}H',self.data,offset)
        rgba=bytearray(256*128*4)
        for y in range(128):
            src,x,count=struct.unpack_from('<HHH',self.data,22+y*12)
            if x+count>256 or src+count>self.pixels:raise ValueError('손상된 타일 마스크')
            for n,value in enumerate(packed[src:src+count]):
                at=(y*256+x+n)*4
                rgba[at:at+4]=bytes((((value>>11)&31)*255//31,((value>>5)&63)*255//63,(value&31)*255//31,255))
        result=Image.frombytes('RGBA',(256,128),bytes(rgba))
        self.cache[index]=result
        return result

    def render(self,model,scale=5):
        output=Image.new('RGB',((model.columns*8+12)*scale,(model.rows*2+4)*scale),'#182329')
        resized={}
        for i in range(model.columns*model.rows):
            tile_id=int.from_bytes(model.record(i)[:2],'little')
            if tile_id not in resized:
                resized[tile_id]=self.tile(tile_id).resize((8*scale,4*scale),Image.Resampling.LANCZOS)
            row,col=divmod(i,model.columns)
            tile=resized[tile_id]
            output.paste(tile,((col*8+row%2*4)*scale,row*2*scale),tile)
        for _,record in sorted(model.resources(),key=lambda entry:struct.unpack_from('<I',entry[1],12)[0]):
            resource_id=struct.unpack_from('<H',record,4)[0]
            sprite,dx,dy=self.resources.get(resource_id)
            x,y=struct.unpack_from('<II',record,8)
            image=sprite.resize((max(1,round(sprite.width*scale/32)),max(1,round(sprite.height*scale/32))),Image.Resampling.LANCZOS)
            output.paste(image,(round(x*scale+dx*scale/32),round(y*scale+dy*scale/32)),image)
        return output


class ResourceTextures:
    def __init__(self,theme,data_dir=DATA):
        prefix='EWSD'[theme]
        bld=read_asset(f'DATA\\IMAGE\\{prefix}_OBJECT.BLD',data_dir)
        data=read_asset(f'DATA\\IMAGE\\{prefix}_OBJECT.S16',data_dir)
        groups=struct.unpack_from('<H',data,16)[0]
        counts=struct.unpack_from(f'<{groups}H',data,18)
        frames=sprites565(data)
        objects=struct.unpack_from('<I',bld)[0]
        self.images={}
        # Four installed BLD sets end in the two resource definitions. Validate
        # fixed tail layouts instead of guessing sprite indices from object IDs.
        for object_id,position,footprint in ((objects-2,len(bld)-164,2),(objects-1,len(bld)-60,1)):
            dx,dy,zero,group,width,height=struct.unpack_from('<iiiIii',bld,position-12)
            if zero!=0 or width!=3 or height!=footprint or group>=groups or not counts[group]:
                raise ValueError('지원하지 않는 자원 BLD 구조')
            sprite,left,top=frames[sum(counts[:group])]
            self.images[object_id]=(sprite,dx+left,dy+top)

    def get(self,object_id):
        if object_id not in self.images:raise ValueError(f'미지원 자원 이미지 ID {object_id}')
        return self.images[object_id]
