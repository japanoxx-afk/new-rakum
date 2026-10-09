"""Conservative native RKM editing. Unknown chunks are preserved verbatim."""
from pathlib import Path
import struct


class RkmMap:
    @classmethod
    def new_blank(cls, template, terrain=None):
        """New empty layout using a verified multiplayer header/start preset."""
        model=cls(template)
        palette=list(model.palette)
        terrain=terrain or model.palette[0]
        if terrain not in palette:raise ValueError('기본 지형 견본을 선택하세요.')
        chunks=[bytes(model.data[a:b]) for a,b in model.sections]
        chunks[2]=terrain*(model.columns*model.rows)
        chunks[3]=bytes(8)  # zero units and zero map objects/resources
        chunks[6]=bytes(4)  # zero animated terrain/decorations (0040D6B0)
        header=bytearray(model.data[:76]);offset=76
        for i,chunk in enumerate(chunks):
            struct.pack_into('<I',header,16+i*8,offset);offset+=len(chunk)
        result=cls(header+b''.join(chunks))
        result.palette=palette
        return result

    def __init__(self, data):
        self.original = bytes(data)
        self.data = bytearray(data)
        if len(data)<76 or data[:4]!=b'J2M\0':
            raise ValueError('지원하는 J2M/RKM 맵이 아닙니다. WGM은 변환할 수 없습니다.')
        count=struct.unpack_from('<I',data,4)[0]
        if count!=8:
            raise ValueError('지원하지 않는 섹션 수입니다.')
        entries=[struct.unpack_from('<II',data,12+i*8) for i in range(count)]
        if [i for i,_ in entries]!=list(range(8)):
            raise ValueError('지원하지 않는 섹션 배열입니다.')
        offsets=[off for _,off in entries]+[len(data)]
        if offsets[0]!=76 or any(a>b or a<76 for a,b in zip(offsets,offsets[1:])):
            raise ValueError('손상된 섹션 범위입니다.')
        self.sections=[(a,b) for a,b in zip(offsets,offsets[1:])]
        if offsets[1]-offsets[0]!=20:
            raise ValueError('지원하지 않는 맵 헤더입니다.')
        self.width,self.height=struct.unpack_from('<HH',data,offsets[0]+8)
        if not (8<=self.width<=512 and 8<=self.height<=512):
            raise ValueError('지원하지 않는 맵 크기입니다.')
        # Native loader 0040B580: Y += 2, X += 8, 5-byte records.
        # Every other row has X += 4 (0040B640..0040B6AA).
        self.columns=(self.width+7)//8
        self.rows=(self.height+1)//2
        self.start,self.end=self.sections[2]
        if self.end-self.start!=self.columns*self.rows*5:
            raise ValueError('지형 배열 크기가 로더 규칙과 일치하지 않습니다.')
        self.palette=sorted(set(self.record(i) for i in range(self.columns*self.rows)))
        a,b=self.sections[3]
        if b-a<8:raise ValueError('오브젝트 헤더가 손상되었습니다.')
        self.object_counts=struct.unpack_from('<II',self.data,a)
        if b-a!=8+20*sum(self.object_counts):raise ValueError('오브젝트 크기가 일치하지 않습니다.')

    def objects(self):
        a,b=self.sections[3]
        return [bytes(self.data[i:i+20]) for i in range(a+8,b,20)]

    def start_points(self):
        # 0040B0E0 reads 8 * 33 team bytes, then player_count * 24 bytes.
        # 0040B177/18A passes record +8 (Y), +6 (X) to 0043A9F0.
        count=self.data[self.sections[0][0]+13]
        a,b=self.sections[1]
        if not 1<=count<=8 or b-a!=264+count*24:
            raise ValueError('지원하지 않는 플레이어 시작 위치 구조입니다.')
        return [struct.unpack_from('<HH',self.data,a+264+i*24+6) for i in range(count)]

    def set_start_point(self,player,x,y):
        points=self.start_points()
        if type(player) is not int or not 0<=player<len(points):
            raise ValueError('플레이어를 선택하세요.')
        if any(type(v) is not int for v in (x,y)) or not (4<=x<self.width-4 and 4<=y<self.height-4):
            raise ValueError('시작 위치는 맵 가장자리 밖에 배치할 수 없습니다.')
        if any(p==(x,y) for i,p in enumerate(points) if i!=player):
            raise ValueError('다른 플레이어의 시작 위치와 겹칩니다.')
        before=points[player]
        struct.pack_into('<HH',self.data,self.sections[1][0]+264+player*24+6,x,y)
        return before

    def validate_starts(self):
        issues=[];seen=set()
        for i,(x,y) in enumerate(self.start_points()):
            if not (4<=x<self.width-4 and 4<=y<self.height-4):
                issues.append(f'P{i+1}: 시작 위치가 맵 가장자리 또는 경계 밖입니다.')
            if (x,y) in seen:issues.append(f'P{i+1}: 시작 위치가 중복됩니다.')
            seen.add((x,y))
        return issues

    def resources(self):
        # Loader 0040CCD0 type 7: +8/+12 coordinates, +16 quantity.
        return [(i,r) for i,r in enumerate(self.objects()) if i>=self.object_counts[0] and r[2]==7]

    def replace_objects(self,records):
        old=self.objects()
        fixed=self.object_counts[0]
        if records[:fixed]!=old[:fixed] or [r for r in records[fixed:] if r[2]!=7]!=[r for r in old[fixed:] if r[2]!=7]:
            raise ValueError('자원 외 오브젝트는 변경할 수 없습니다.')
        if any(len(r)!=20 for r in records):raise ValueError('잘못된 레코드입니다.')
        chunks=[bytes(self.data[a:b]) for a,b in self.sections]
        chunks[3]=struct.pack('<II',fixed,len(records)-fixed)+b''.join(records)
        header=bytearray(self.data[:76]);offset=76
        for i,chunk in enumerate(chunks):
            struct.pack_into('<I',header,16+i*8,offset);offset+=len(chunk)
        candidate=RkmMap(header+b''.join(chunks))
        self.data=candidate.data;self.sections=candidate.sections
        self.object_counts=candidate.object_counts

    def add_resource(self,template,x,y,amount=None):
        if template not in self.resource_templates()+[r for _,r in self.resources()]:raise ValueError('기존 자원 견본을 선택하세요.')
        if not (4<=x<self.width-4 and 4<=y<self.height-4):raise ValueError('맵 가장자리에는 배치할 수 없습니다.')
        if any(struct.unpack_from('<II',r,8)==(x,y) for _,r in self.resources()):
            raise ValueError('같은 위치에 자원이 있습니다.')
        record=bytearray(template);struct.pack_into('<II',record,8,x,y)
        if amount is not None:
            self.check_amount(amount);struct.pack_into('<I',record,16,amount)
        self.replace_objects(self.objects()+[bytes(record)])

    @staticmethod
    def check_amount(amount):
        if type(amount) is not int or not 1<=amount<=1000000:
            raise ValueError('매장량은 1~1,000,000 사이 정수여야 합니다.')

    def set_resource_amount(self,index,amount):
        self.check_amount(amount)
        if index not in [i for i,_ in self.resources()]:raise ValueError('자원을 선택하세요.')
        records=self.objects();record=bytearray(records[index])
        struct.pack_into('<I',record,16,amount);records[index]=bytes(record)
        self.replace_objects(records)

    def resource_templates(self):
        theme=struct.unpack_from('<I',self.data,76)[0]
        ids=((20,21),(17,18),(17,18),(10,11))
        if theme not in range(4):raise ValueError('지원하지 않는 자원 테마')
        return [struct.pack('<4BHBBIII',0,0,7,0,object_id,kind,0,0,0,3000 if kind==0 else 5000)
                for kind,object_id in enumerate(ids[theme])]

    def remove_resource(self,index):
        if index not in [i for i,_ in self.resources()]:raise ValueError('자원만 삭제할 수 있습니다.')
        records=self.objects();del records[index];self.replace_objects(records)

    def validate_resources(self):
        issues=[];seen=set()
        for index,r in self.resources():
            x,y=struct.unpack_from('<II',r,8)
            if not (0<=x<self.width-4 and 0<=y<self.height-4):
                issues.append(f'자원 {index}: 맵 경계 밖 ({x}, {y})')
            if (x,y) in seen:issues.append(f'자원 {index}: 중복 위치 ({x}, {y})')
            seen.add((x,y))
        return issues

    def record(self,index):
        if not 0<=index<self.columns*self.rows:
            raise IndexError(index)
        start=self.start+index*5
        return bytes(self.data[start:start+5])

    def paint(self,index,record):
        if record not in self.palette:
            raise ValueError('같은 맵에서 확인한 견본만 사용할 수 있습니다.')
        before=self.record(index)
        self.data[self.start+index*5:self.start+index*5+5]=record
        return before

    def export(self,path,source=None):
        path=Path(path)
        if path.suffix.lower()!='.rkm':
            raise ValueError('.rkm 확장자가 필요합니다.')
        if source and path.resolve()==Path(source).resolve():
            raise ValueError('원본에는 저장할 수 없습니다. 새 이름을 지정하세요.')
        candidate=RkmMap(self.data);original=RkmMap(self.original)
        for i in (0,4,5,6,7):
            a,b=candidate.sections[i];c,d=original.sections[i]
            if candidate.data[a:b]!=original.data[c:d]:raise ValueError('보호된 섹션이 변경되었습니다.')
        a,b=candidate.sections[1];c,d=original.sections[1]
        start_data=bytearray(candidate.data[a:b]);old=original.data[c:d]
        if start_data!=old:
            points=candidate.start_points();original.start_points()
            issues=candidate.validate_starts()
            if issues:raise ValueError('\n'.join(issues))
            for player in range(len(points)):
                offset=264+player*24+6
                start_data[offset:offset+4]=old[offset:offset+4]
            if start_data!=old:raise ValueError('시작 좌표 외 플레이어 설정이 변경되었습니다.')
        fixed=original.object_counts[0]
        if candidate.object_counts[0]!=fixed or candidate.objects()[:fixed]!=original.objects()[:fixed]:
            raise ValueError('시작 오브젝트가 변경되었습니다.')
        if [r for r in candidate.objects()[fixed:] if r[2]!=7]!=[r for r in original.objects()[fixed:] if r[2]!=7]:
            raise ValueError('자원 외 오브젝트가 변경되었습니다.')
        with path.open('xb') as output:
            output.write(self.data)
