"""Standalone experimental RhakMu native-map terrain editor."""
from pathlib import Path
import hashlib
import struct
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from rkm_format import RkmMap
from map_textures import TerrainTextures
from terrain_palette import TerrainPalette, CATEGORIES
from PIL import ImageTk

MAPS=Path(r'C:\Program Files (x86)\TriggerSoft\RhakMu\Data\Maps')


class Editor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('라크무 맵 편집기 — 지형·자원·시작 위치 0.5')
        self.geometry('1200x820')
        self.minsize(800,600)
        self.model=None
        self.new_unsaved=False
        self.source=None
        self.history=[]
        self.stroke={}
        self.items={}
        self.resource_items={}
        self.scale=5
        self.textures=None
        self.background=None
        bar=ttk.Frame(self,padding=10)
        bar.pack(fill='x')
        ttk.Button(bar,text='맵 열기',command=self.open_map).pack(side='left')
        ttk.Button(bar,text='새 빈 맵',command=self.new_map).pack(side='left',padx=4)
        ttk.Button(bar,text='새 이름으로 복사본 저장',command=self.save_map).pack(side='left',padx=8)
        ttk.Button(bar,text='실행 취소',command=self.undo).pack(side='left')
        ttk.Button(bar,text='확대',command=lambda:self.zoom(1)).pack(side='left',padx=8)
        ttk.Button(bar,text='축소',command=lambda:self.zoom(-1)).pack(side='left')
        ttk.Button(bar,text='맵 검사',command=self.validate_map).pack(side='left',padx=8)
        terrain_bar=ttk.Frame(self,padding=8);terrain_bar.pack(fill='x')
        ttk.Label(terrain_bar,text='지형 분류').pack(side='left')
        self.category=ttk.Combobox(terrain_bar,state='readonly',width=10,values=CATEGORIES)
        self.category.pack(side='left',padx=6)
        self.category.bind('<<ComboboxSelected>>',lambda e:self.refresh_families())
        self.palette=ttk.Combobox(terrain_bar,state='readonly',width=25)
        self.palette.pack(side='left',padx=6)
        self.palette.bind('<<ComboboxSelected>>',lambda e:self.refresh_variants())
        self.details=tk.BooleanVar(value=False)
        ttk.Checkbutton(terrain_bar,text='세부 타일 선택',variable=self.details,command=self.toggle_details).pack(side='left')
        self.variant=ttk.Combobox(terrain_bar,state='readonly',width=28)
        self.variant.bind('<<ComboboxSelected>>',lambda e:self.show_sample())
        self.sample_label=ttk.Label(terrain_bar)
        self.sample_label.pack(side='right',padx=8)
        ttk.Label(self,text='왼쪽 드래그: 칠하기 · 오른쪽 클릭: 견본 추출 · Ctrl+Z: 실행 취소\n'
                  '지형: 대표 견본 → 필요 시 세부 타일 선택. 입구 분류는 외형 기준이며 자동 접합·통행 검사는 지원하지 않습니다.',
                  padding=10).pack(fill='x')
        resource_bar=ttk.Frame(self,padding=8);resource_bar.pack(fill='x')
        self.mode=tk.StringVar(value='지형')
        for mode in ('지형','자원 배치','자원량 수정','자원 삭제'):
            ttk.Radiobutton(resource_bar,text=mode,variable=self.mode,value=mode).pack(side='left',padx=6)
        self.resource_palette=ttk.Combobox(resource_bar,state='readonly',width=12)
        self.resource_palette.pack(side='left',padx=15)
        ttk.Label(resource_bar,text='매장량').pack(side='left')
        self.amount=tk.StringVar(value='3000')
        ttk.Spinbox(resource_bar,from_=1,to=1000000,textvariable=self.amount,width=10).pack(side='left',padx=4)
        self.resource_palette.bind('<<ComboboxSelected>>',lambda e:self.amount.set('3000' if self.resource_palette.current()==0 else '5000'))
        ttk.Button(resource_bar,text='게임 자원량 패치',command=self.patch_amount).pack(side='left',padx=8)
        ttk.Button(resource_bar,text='패치 해제',command=lambda:self.patch_amount(False)).pack(side='left')
        start_bar=ttk.Frame(self,padding=8);start_bar.pack(fill='x')
        ttk.Radiobutton(start_bar,text='스타팅 포인트 배치',variable=self.mode,value='시작 위치').pack(side='left')
        self.player_palette=ttk.Combobox(start_bar,state='readonly',width=12)
        self.player_palette.pack(side='left',padx=8)
        ttk.Label(start_bar,text='플레이어 선택 → 지도 클릭으로 이동 · 번호 표시 우클릭으로 선택 · 인원수는 기본 맵 설정 유지').pack(side='left')
        frame=ttk.Frame(self)
        frame.pack(fill='both',expand=True)
        self.canvas=tk.Canvas(frame,background='#182329',highlightthickness=0)
        sx=ttk.Scrollbar(frame,orient='horizontal',command=self.canvas.xview)
        sy=ttk.Scrollbar(frame,orient='vertical',command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=sx.set,yscrollcommand=sy.set)
        self.canvas.grid(row=0,column=0,sticky='nsew')
        sy.grid(row=0,column=1,sticky='ns')
        sx.grid(row=1,column=0,sticky='ew')
        frame.rowconfigure(0,weight=1)
        frame.columnconfigure(0,weight=1)
        self.status=tk.StringVar(value='기존 .rkm 맵을 열어 시작하세요. 원본 게임 파일은 변경하지 않습니다.')
        ttk.Label(self,textvariable=self.status,padding=10).pack(fill='x')
        self.canvas.bind('<Button-1>',self.paint)
        self.canvas.bind('<B1-Motion>',self.paint)
        self.canvas.bind('<ButtonRelease-1>',self.finish_stroke)
        self.canvas.bind('<Button-3>',self.sample)
        self.bind('<Control-z>',lambda e:self.undo())
        self.protocol('WM_DELETE_WINDOW',self.close)

    def discard_ok(self):
        return not self.model or (not self.new_unsaved and self.model.data==self.model.original) or messagebox.askyesno(
            '변경 확인','편집 중인 변경 내용을 닫아도 될까요?')

    def close(self):
        if self.discard_ok(): self.destroy()

    def open_map(self):
        if not self.discard_ok(): return
        path=filedialog.askopenfilename(initialdir=str(MAPS),filetypes=[('라크무 맵','*.rkm')])
        if not path:return
        try:
            model=RkmMap(Path(path).read_bytes())
            textures=TerrainTextures(struct.unpack_from('<I',model.data,76)[0])
        except (OSError,ValueError) as exc:
            messagebox.showerror('열기 실패',str(exc));return
        self.load_model(model,Path(path),textures)

    def new_map(self):
        if not self.discard_ok():return
        messagebox.showinfo('새 빈 맵', '크기·테마·인원·시작 위치의 기본 설정으로 사용할 맵을 선택하세요.\n'
            '지형은 기본 타일로 초기화하고 자원·장식물·배치 오브젝트를 제거합니다.\n'
            '현재 버전은 임의 크기 지정 대신 검증된 맵 설정을 사용합니다.')
        path=filedialog.askopenfilename(title='새 맵 기본 설정 선택',initialdir=str(MAPS),filetypes=[('라크무 맵','*.rkm')])
        if not path:return
        try:
            model=RkmMap.new_blank(Path(path).read_bytes())
            textures=TerrainTextures(struct.unpack_from('<I',model.data,76)[0])
            self.load_model(model,Path('NewMap.rkm'),textures)
            self.new_unsaved=True
        except (ValueError,OSError) as exc:messagebox.showerror('새 맵 실패',str(exc))

    def patch_amount(self,enabled=True):
        if not messagebox.askyesno('자원량 패치',
            ('일반 멀티플레이가 맵의 매장량을 사용하도록 게임 파일을 패치합니다. 모든 참가자에게 같은 패치가 필요합니다.\n'
             if enabled else '게임의 고정 매장량 로더로 복원합니다.\n')+
            '게임 종료 필요 · 확인된 설치본만 지원 · 원본 백업 생성. 계속할까요?'):return
        path=filedialog.askopenfilename(title='설치본 Rhakmu.exe 선택',initialdir=str(MAPS.parent.parent),filetypes=[('게임 실행 파일','Rhakmu.exe')])
        if not path:return
        try:
            from resource_amount_patch import apply
            apply(path,enabled)
            messagebox.showinfo('완료','게임 자원량 패치 적용 완료' if enabled else '게임 자원량 패치 해제 완료')
        except Exception as exc:messagebox.showerror('패치 실패',str(exc))

    def load_model(self,model,path,textures):
        self.model,self.source=model,Path(path)
        self.new_unsaved=False
        self.textures=textures
        self.history=[];self.stroke={}
        self.terrain_catalog=TerrainPalette(model)
        self.category.current(0)
        self.refresh_families()
        self.player_palette['values']=[f'플레이어 {i+1}' for i in range(len(model.start_points()))]
        self.player_palette.current(0)
        self.refresh_resources()
        self.redraw()

    def refresh_resources(self):
        selected=self.resource_palette.current()
        self.resource_templates=self.model.resource_templates()
        self.resource_palette['values']=['자원 1 (푸른색)','자원 2 (황금색)']
        if self.resource_templates:self.resource_palette.current(max(0,selected))
        else:self.resource_palette.set('이 맵에는 복제할 자원이 없습니다.')

    def refresh_families(self):
        if not self.model:return
        families=self.terrain_catalog.groups[self.category.get()]
        self.family_names=list(families)
        self.palette['values']=[f'{name} ({len(families[name])}종)' for name in self.family_names]
        if self.family_names:self.palette.current(0)
        else:self.palette.set('이 맵에 견본 없음')
        self.refresh_variants()

    def refresh_variants(self):
        n=self.palette.current()
        self.visible_records=(self.terrain_catalog.groups[self.category.get()][self.family_names[n]]
                              if n>=0 and self.family_names else [])
        self.variant['values']=[f'ID {int.from_bytes(r[:2],"little")} | {r[2:].hex(" ")}' for r in self.visible_records]
        if self.visible_records:self.variant.current(0)
        else:self.variant.set('')
        self.show_sample()

    def toggle_details(self):
        if self.details.get():self.variant.pack(side='left',padx=8)
        else:self.variant.pack_forget()

    def selected_record(self):
        n=self.variant.current()
        return self.visible_records[n] if n>=0 and self.visible_records else None

    def show_sample(self):
        if not self.model or not self.textures:return
        record=self.selected_record()
        if record is None:
            self.sample_label.configure(image='');return
        tile_id=int.from_bytes(record[:2],'little')
        self.sample_image=ImageTk.PhotoImage(self.textures.tile(tile_id).resize((128,64)))
        self.sample_label.configure(image=self.sample_image)

    def validate_map(self):
        if not self.model:return
        issues=self.model.validate_resources()+self.model.validate_starts()
        messagebox.showinfo('맵 검사', '\n'.join(issues) if issues else
            '자원·시작 위치 좌표 및 중복 검사 통과.\n시작 좌표 외 플레이어 설정과 비자원 데이터는 보존합니다.\n'
            '지형/장식물 충돌·채집 가능 여부·멀티플레이 동기화는 게임에서 확인해야 합니다.')

    @staticmethod
    def color(record):
        digest=hashlib.sha256(record).digest()
        return '#'+''.join(f'{60+x%150:02x}' for x in digest[:3])

    def redraw(self):
        self.canvas.delete('all');self.items={};self.resource_items={}
        if not self.model:return
        s=self.scale
        if self.textures:
            self.background=ImageTk.PhotoImage(self.textures.render(self.model,s))
            self.canvas.create_image(20,20,image=self.background,anchor='nw')
        for index in range(self.model.columns*self.model.rows):
            row,col=divmod(index,self.model.columns)
            x=(col*8+(row%2)*4)*s+20;y=row*2*s+20
            item=self.canvas.create_polygon(x+4*s,y,x+8*s,y+2*s,x+4*s,y+4*s,x,y+2*s,
                fill='' if self.textures else self.color(self.model.record(index)),outline='',tags=('terrain',))
            self.items[item]=index
        for index,r in self.model.resources():
            x,y=struct.unpack_from('<II',r,8);x=x*s+20;y=y*s+20
            item=self.canvas.create_oval(x-6,y-6,x+6,y+6,fill='',outline='#ffd35c',width=1)
            self.resource_items[item]=index
        colors=('#ff6666','#66aaff','#70e080','#ffe070','#d490ff','#66eeee','#ffaa60','#f6a9d0')
        for i,(x,y) in enumerate(self.model.start_points()):
            x=x*s+20;y=y*s+20
            self.canvas.create_oval(x-13,y-13,x+13,y+13,fill='#182329',outline=colors[i],width=3)
            self.canvas.create_text(x,y,text=str(i+1),fill=colors[i],font=('Arial',11,'bold'))
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))
        self.status.set(f'{self.source.name} | 헤더 크기 {self.model.width}×{self.model.height} | '
                        f'지형 레코드 {self.model.columns*self.model.rows}개 | 실제 게임 호환성 시험 필요')

    def hit(self,event):
        x,y=self.canvas.canvasx(event.x),self.canvas.canvasy(event.y)
        # Unfilled Tk polygons do not reliably hit-test their interior.
        for item,index in reversed(list(self.items.items())):
            row,col=divmod(index,self.model.columns)
            cx=(col*8+row%2*4+4)*self.scale+20
            cy=(row*2+2)*self.scale+20
            if abs(x-cx)/(4*self.scale)+abs(y-cy)/(2*self.scale)<=1:
                return item
        return None

    def paint(self,event):
        if not self.model:return
        if self.mode.get()=='시작 위치':
            if event.type!=tk.EventType.ButtonPress:return
            self.finish_stroke()
            player=self.player_palette.current()
            x=round((self.canvas.canvasx(event.x)-20)/self.scale)
            y=round((self.canvas.canvasy(event.y)-20)/self.scale)
            try:before=self.model.set_start_point(player,x,y)
            except ValueError as exc:self.status.set(str(exc));return
            if before!=(x,y):self.history.append(('start',(player,before)))
            self.redraw();self.status.set(f'플레이어 {player+1} 시작 위치: ({x}, {y}) — 지형 통행·기지 생성 공간은 게임에서 확인하세요.')
            return
        if self.mode.get()!='지형':
            if event.type!=tk.EventType.ButtonPress:return
            self.finish_stroke()
            before=self.model.objects()
            try:
                if self.mode.get()=='자원 배치':
                    n=self.resource_palette.current()
                    if n<0:return
                    x=round((self.canvas.canvasx(event.x)-20)/self.scale)
                    y=round((self.canvas.canvasy(event.y)-20)/self.scale)
                    self.model.add_resource(self.resource_templates[n],x,y,int(self.amount.get()))
                else:
                    index=self.resource_hit(event)
                    if index is None:return
                    if self.mode.get()=='자원량 수정':
                        self.model.set_resource_amount(index,int(self.amount.get()))
                    else:self.model.remove_resource(index)
            except ValueError as exc:
                self.status.set(str(exc));return
            self.history.append(('resources',before))
            self.refresh_resources();self.redraw();return
        item=self.hit(event)
        if item is None:return
        record=self.selected_record()
        if record is None:return
        index=self.items[item]
        before=self.model.paint(index,record)
        self.stroke.setdefault(index,before)
        self.canvas.itemconfigure(item,fill='',outline='#ffffff')

    def sample(self,event):
        if not self.model:return
        x,y=self.canvas.canvasx(event.x),self.canvas.canvasy(event.y)
        for i,(sx,sy) in enumerate(self.model.start_points()):
            if (x-(sx*self.scale+20))**2+(y-(sy*self.scale+20))**2<=169:
                self.player_palette.current(i);self.mode.set('시작 위치')
                self.status.set(f'플레이어 {i+1} 선택 — 이동할 위치를 클릭하세요.');return
        index=self.resource_hit(event)
        if index is not None:
            record=self.model.objects()[index]
            self.resource_palette.current(1 if record[6] else 0)
            self.amount.set(str(struct.unpack_from('<I',record,16)[0]))
            self.status.set('자원 선택: 매장량 입력 후 「자원량 수정」 모드에서 해당 자원을 클릭하세요.')
            return
        item=self.hit(event)
        if item is not None:
            category,family,n=self.terrain_catalog.locate(self.model.record(self.items[item]))
            self.category.set(category);self.refresh_families()
            self.palette.current(self.family_names.index(family));self.refresh_variants()
            self.variant.current(n)
            self.details.set(True);self.toggle_details()
            self.show_sample()

    def resource_hit(self,event):
        if not self.model:return None
        x,y=self.canvas.canvasx(event.x),self.canvas.canvasy(event.y)
        nearest=None;distance=100
        for index,record in self.model.resources():
            rx,ry=struct.unpack_from('<II',record,8)
            squared=(x-(rx*self.scale+20))**2+(y-(ry*self.scale+20))**2
            if squared<=distance:nearest=index;distance=squared
        return nearest

    def finish_stroke(self,event=None):
        if self.stroke:
            self.history.append(('terrain',self.stroke));self.stroke={};self.redraw()

    def undo(self):
        self.finish_stroke()
        if not self.history:return
        kind,changes=self.history.pop()
        if kind=='terrain':
            for index,before in changes.items():self.model.paint(index,before)
        elif kind=='start':
            player,(x,y)=changes
            # Restore exact original coordinates, including legacy edge positions.
            struct.pack_into('<HH',self.model.data,self.model.sections[1][0]+264+player*24+6,x,y)
        else:
            self.model.replace_objects(changes);self.refresh_resources()
        self.redraw()

    def zoom(self,delta):
        self.scale=max(2,min(14,self.scale+delta));self.redraw()

    def save_map(self):
        if not self.model:return
        self.finish_stroke()
        path=filedialog.asksaveasfilename(initialfile=self.source.stem+'_edited.rkm',
             defaultextension='.rkm',filetypes=[('라크무 맵','*.rkm')])
        if not path:return
        try:self.model.export(path,self.source)
        except (ValueError,OSError) as exc:
            messagebox.showerror('저장 실패',str(exc));return
        self.new_unsaved=False
        self.status.set(f'저장: {path} — 사용자 지정 매장량은 모든 참가자의 게임 자원량 패치가 필요합니다.')


if __name__=='__main__':
    Editor().mainloop()
