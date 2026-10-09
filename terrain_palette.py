"""Visual families of the four local JTL sets; never discard record metadata.

Classification is an editor aid, not an assertion about native passability.
All five bytes of every observed variant remain independently selectable.
"""
from collections import Counter

CATEGORIES=('언덕','입구','평지 타일')


def family_for(theme,tile):
    if not 0<=theme<4:raise ValueError('지원하지 않는 테마')
    if 0<=tile<30:
        names=(('물가 바닥','흙','풀밭'),('얼음 바닥','흙','눈밭'),
               ('황토','모래','석재 바닥'),('용암 바닥','흙','석재 바닥'))[theme]
        return '평지 타일',names[tile//10]
    if 30<=tile<52:return '언덕','낮은 언덕·절벽'
    if 52<=tile<70:return '평지 타일','바닥 경계·연결'
    if 70<=tile<114:return '언덕','높은 언덕·절벽'
    if theme==2:
        if 114<=tile<132:return '언덕','낮은 석벽'
        if 132<=tile<138:return '입구','계단·경사 연결'
        if 138<=tile<162:return '언덕','복합 절벽'
        if 162<=tile<185:return '언덕','석벽 모서리'
    else:
        if 114<=tile<124:return '입구','계단·경사 연결'
        if 124<=tile<138:return '언덕','언덕 끝·모서리'
        if 138<=tile<162:return '언덕','복합 절벽'
        if 162<=tile<185:return '언덕','물가·용암 경계' if theme==3 else '물가 절벽·모서리'
    if 185<=tile<200:return '평지 타일','바닥 무늬·변형'
    return '평지 타일','기타 (미분류)'


class TerrainPalette:
    def __init__(self,model):
        self.theme=int.from_bytes(model.data[76:80],'little')
        counts=Counter(model.record(i) for i in range(model.columns*model.rows))
        self.groups={category:{} for category in CATEGORIES}
        for record in model.palette:
            category,family=family_for(self.theme,int.from_bytes(record[:2],'little'))
            self.groups[category].setdefault(family,[]).append(record)
        # Default to the most common complete record, not synthetic flags.
        for families in self.groups.values():
            for records in families.values():
                records.sort(key=lambda r:(-counts[r],int.from_bytes(r[:2],'little'),r))

    def locate(self,record):
        category,family=family_for(self.theme,int.from_bytes(record[:2],'little'))
        return category,family,self.groups[category][family].index(record)
