"""Device-independent Tk coordinates, native pixel fonts and per-monitor DPI.

The existing UI uses logical pixels. This root-scoped Tcl adapter converts
only presentation dimensions; caption values, units and processing stay intact.
"""
import ctypes
import math
import re
import sys
import tkinter as tk

PIXELS = {'-padx','-pady','-ipadx','-ipady','-borderwidth','-bd',
          '-highlightthickness','-insertwidth','-selectborderwidth','-wraplength',
          '-length','-sliderlength','-spacing1','-spacing2','-spacing3',
          '-minsize','-xscrollincrement','-yscrollincrement','-padding','-x','-y','-pad'}
BOXES = {'canvas','frame','labelframe','toplevel','ttk::frame','ttk::labelframe'}
WIDGETS = BOXES | {'label','entry','text','button','checkbutton','radiobutton',
                   'listbox','scale','scrollbar','ttk::label','ttk::entry',
                   'ttk::button','ttk::checkbutton','ttk::scrollbar'}
GEOMETRY = re.compile(r'^(?:(\d+)x(\d+))?([+-]\d+)?([+-]\d+)?$')


def enable():
    if sys.platform != 'win32':
        return
    try:
        fn = ctypes.windll.user32.SetProcessDpiAwarenessContext
        fn.argtypes = [ctypes.c_void_p]; fn.restype = ctypes.c_bool
        if fn(ctypes.c_void_p(-4)):
            return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        pass


def monitor(root, raw):
    if sys.platform != 'win32':
        return 96, (0,0,int(raw.call('winfo','screenwidth','.')),int(raw.call('winfo','screenheight','.')))
    try:
        from ctypes import wintypes
        class INFO(ctypes.Structure):
            _fields_ = [('size',wintypes.DWORD),('monitor',wintypes.RECT),('work',wintypes.RECT),('flags',wintypes.DWORD)]
        u = ctypes.windll.user32
        hwnd = int(str(raw.call('winfo','id',root._w)),16)
        u.GetDpiForWindow.argtypes=[ctypes.c_void_p];u.GetDpiForWindow.restype=wintypes.UINT
        u.MonitorFromWindow.argtypes=[ctypes.c_void_p,wintypes.DWORD];u.MonitorFromWindow.restype=ctypes.c_void_p
        u.GetMonitorInfoW.argtypes=[ctypes.c_void_p,ctypes.POINTER(INFO)]
        info=INFO();info.size=ctypes.sizeof(info)
        if not u.GetMonitorInfoW(u.MonitorFromWindow(hwnd,2),ctypes.byref(info)):
            raise OSError('monitor lookup')
        r=info.work
        return u.GetDpiForWindow(hwnd) or 96,(r.left,r.top,r.right-r.left,r.bottom-r.top)
    except (AttributeError,OSError,ValueError):
        return 96,(0,0,int(raw.call('winfo','screenwidth',root._w)),int(raw.call('winfo','screenheight',root._w)))


def fit_scale(requested, work):
    # Keep all Master Studio settings visible on smaller scaled displays.
    return max(.5,min(requested,work[2]/1080,work[3]/768))


class LogicalTk:
    def __init__(self, root, scale, work):
        self.raw=root.tk;self.root=root;self.scale=scale;self.work=work
        self.kinds={root._w:'toplevel'}
        self.options={};self.fonts={};self.layouts={};self.items={}

    def __getattr__(self,name):
        return getattr(self.raw,name)

    def pixels(self,value):
        return int(math.floor(float(value)*self.scale+.5))

    def logical(self,value):
        return int(round(float(value)/self.scale))

    def distance(self,value,inverse=False):
        fn=self.logical if inverse else self.pixels
        if isinstance(value,(tuple,list)):
            return tuple(self.distance(v,inverse) for v in value)
        try:
            return fn(value)
        except (ValueError,TypeError):
            return value

    def font(self,value,inverse=False):
        if not isinstance(value,(str,tuple,list)):
            return value
        parts=self.raw.splitlist(value) if isinstance(value,str) else list(value)
        if len(parts)<2:
            return value
        try:
            size=int(parts[1])
        except (TypeError,ValueError):
            return value
        parts=list(parts)
        parts[1]=-self.logical(abs(size)) if inverse else -self.pixels(round(abs(size) if size<0 else size*96/72))
        return tuple(parts)

    def opts(self, values, kind='', inverse=False, canvas=False):
        out=list(values)
        for i in range(0,len(out)-1,2):
            key=str(out[i]);value=out[i+1]
            if key=='-font':
                out[i+1]=self.font(value,inverse)
            elif key in PIXELS or key=='-width' and (kind in BOXES or canvas) or key=='-height' and kind in BOXES:
                out[i+1]=self.distance(value,inverse)
            elif key=='-scrollregion':
                out[i+1]=tuple(self.distance(v,inverse) for v in self.raw.splitlist(value))
        return tuple(out)

    def geometry(self,value,inverse=False):
        match=GEOMETRY.match(str(value))
        if not match or not value:
            return value
        w,h,x,y=match.groups();fn=self.logical if inverse else self.pixels
        text=f'{fn(w)}x{fn(h)}' if w else ''
        for v in (x,y):
            if v is not None:
                text+=('+' if v[0]=='+' else '-')+str(fn(abs(int(v))))
        return text

    def remember(self, store, key, options):
        store.setdefault(key,{}).update(dict(zip(options[::2],options[1::2])))

    def item_ids(self,path,tag):
        return self.raw.splitlist(self.raw.call(path,'find','withtag',tag))

    def call(self,*args):
        if len(args)==1 and isinstance(args[0],(tuple,list)):
            args=tuple(args[0])
        while args and args[-1] is None:
            args=args[:-1]
        if not args:
            return self.raw.call(*args)
        cmd=str(args[0]);a=list(args)
        if cmd in WIDGETS and len(a)>1:
            path=str(a[1]);self.kinds[path]=cmd
            self.remember(self.options,path,a[2:]);a[2:]=self.opts(a[2:],cmd)
        elif cmd=='font' and len(a)>2:
            sub=str(a[1]);name=str(a[2])
            known=self.fonts.get(name)
            if sub in ('actual','measure','metrics'):
                parts=self.raw.splitlist(a[2]) if isinstance(a[2],str) else a[2]
                if isinstance(parts,(tuple,list)) and len(parts)>1:
                    try:
                        size=int(parts[1]);known=-round(abs(size) if size<0 else size*96/72)
                    except (TypeError,ValueError):pass
                a[2]=self.font(a[2])
            if sub in ('create','configure','config') and len(a)>4:
                original=dict(zip(a[3::2],a[4::2]))
                if '-size' in original:
                    size=float(original['-size']);logical=-abs(size) if size<0 else -round(size*96/72)
                    self.fonts[name]=logical
                    index=a.index('-size');a[index+1]=-self.pixels(abs(logical))
            result=self.raw.call(*a)
            if sub=='measure':
                return self.logical(result)
            if sub=='metrics':
                if len(a)>3 and str(a[3]) in ('-ascent','-descent','-linespace'):
                    return self.logical(result)
                if len(a)==3:
                    parts=list(self.raw.splitlist(result))
                    for i in range(0,len(parts),2):
                        if parts[i]!='-fixed':parts[i+1]=self.logical(parts[i+1])
                    return tuple(parts)
            if sub in ('actual','configure','config'):
                if len(a)==4 and str(a[3])=='-size':
                    return known if known is not None else -self.logical(abs(int(result)))
                if len(a)==3:
                    parts=list(self.raw.splitlist(result))
                    if '-size' in parts:
                        i=parts.index('-size');parts[i+1]=known if known is not None else -self.logical(abs(int(parts[i+1])))
                    return tuple(parts)
            return result
        elif cmd in ('pack','grid','place'):
            if len(a)>3 and str(a[1]) in ('configure','columnconfigure','rowconfigure'):
                start=4 if str(a[1])!='configure' else 3
                key=(cmd,tuple(a[1:start]));self.remember(self.layouts,key,a[start:])
                # Place dimensions are pixels; Entry width is characters.
                a[start:]=self.opts(a[start:],'frame' if cmd=='place' else '')
            if len(a)==3 and str(a[1])=='info':
                return self.opts(self.raw.splitlist(self.raw.call(*a)), 'frame' if cmd=='place' else '',inverse=True)
        elif cmd=='wm' and len(a)>2:
            if a[1]=='geometry':
                if len(a)>3:a[3]=self.geometry(a[3])
                result=self.raw.call(*a)
                return self.geometry(result,True) if len(a)==3 else result
            if a[1] in ('minsize','maxsize'):
                if len(a)>3:a[3:]=[self.pixels(v) for v in a[3:]]
                result=self.raw.call(*a)
                return tuple(self.logical(v) for v in self.raw.splitlist(result)) if len(a)==3 else result
        elif cmd=='winfo' and len(a)>2:
            sub=str(a[1])
            if sub=='containing':a[2:4]=[self.pixels(v) for v in a[2:4]]
            if sub=='screenwidth':return self.logical(self.work[2])
            if sub=='screenheight':return self.logical(self.work[3])
            result=self.raw.call(*a)
            if sub in ('width','height','reqwidth','reqheight','x','y','rootx','rooty','vrootx','vrooty','vrootwidth','vrootheight','pixels'):
                return self.logical(result)
            if sub=='fpixels':return float(result)/self.scale
            return result
        elif cmd=='ttk::style' and len(a)>3 and a[1]=='configure':
            a[3:]=self.opts(a[3:])
        elif cmd=='event' and len(a)>3 and a[1]=='generate':
            for i in range(4,len(a)-1,2):
                if a[i] in ('-x','-y','-rootx','-rooty','-width','-height'):
                    a[i+1]=self.pixels(a[i+1])
        elif cmd=='destroy':
            for target in a[1:]:
                for path in list(self.kinds):
                    if path==target or path.startswith(str(target)+'.'):
                        self.kinds.pop(path,None);self.options.pop(path,None);self.items.pop(path,None)
        elif cmd in self.kinds and len(a)>1:
            kind=self.kinds[cmd];sub=str(a[1])
            if kind=='canvas':
                result=self.canvas(a)
                if result is not None:return result[0]
            if sub in ('configure','config') and len(a)>3:
                self.remember(self.options,cmd,a[2:]);a[2:]=self.opts(a[2:],kind)
            if sub=='cget' and len(a)==3:
                result=self.raw.call(*a)
                key=str(a[2])
                if key=='-font':return self.font(result,True)
                if key in PIXELS or key in ('-width','-height') and kind in BOXES:return self.distance(result,True)
                return result
        result=self.raw.call(*a)
        return result

    def canvas(self,a):
        path,sub=str(a[0]),str(a[1]);items=self.items.setdefault(path,{})
        if sub=='create':
            kind=str(a[2])
            # Negative coordinate numbers are coordinates, not option names.
            index=3
            while index<len(a):
                try:float(a[index]);index+=1
                except (TypeError,ValueError):break
            coords=a[3:index];opts=a[index:]
            physical=[float(v)*self.scale for v in coords]
            if kind=='text':physical=[round(v) for v in physical]
            item=self.raw.call(path,'create',kind,*physical,*self.opts(opts,'frame' if kind=='window' else '',canvas=True))
            items[str(item)]=(kind,list(coords),dict(zip(opts[::2],opts[1::2])))
            return (item,)
        if sub=='coords' and len(a)>2:
            if len(a)==3:
                return (tuple(float(v)/self.scale for v in self.raw.splitlist(self.raw.call(*a))),)
            coords=list(a[3:]);physical=[float(v)*self.scale for v in coords]
            ids=self.item_ids(path,a[2])
            result=self.raw.call(path,'coords',a[2],*physical)
            for item in ids:
                if str(item) in items:
                    kind,_,opts=items[str(item)];items[str(item)]=(kind,coords,opts)
            return (result,)
        if sub in ('itemconfigure','itemconfig') and len(a)>4:
            for item in self.item_ids(path,a[2]):
                if str(item) in items:items[str(item)][2].update(dict(zip(a[3::2],a[4::2])))
            return (self.raw.call(path,sub,a[2],*self.opts(a[3:],'frame',canvas=True)),)
        if sub=='delete':
            for tag in a[2:]:
                for item in self.item_ids(path,tag):items.pop(str(item),None)
            return (self.raw.call(*a),)
        if sub=='bbox':
            result=self.raw.call(*a)
            return (tuple(self.logical(v) for v in self.raw.splitlist(result)),)
        if sub=='find' and len(a)>3 and a[2] in ('closest','overlapping','enclosed'):
            count=min(len(a)-3,3 if a[2]=='closest' else 4)
            return (self.raw.call(*a[:3],*[float(v)*self.scale for v in a[3:3+count]],*a[3+count:]),)
        if sub in ('canvasx','canvasy') and len(a)>2:
            return (float(self.raw.call(*a[:2],float(a[2])*self.scale,*a[3:]))/self.scale,)
        if sub in ('move','scale') and len(a)>4:
            ids=self.item_ids(path,a[2]);b=list(a)
            b[3:5]=[float(v)*self.scale for v in b[3:5]]
            result=self.raw.call(*b)
            for item in ids:
                if str(item) in items:
                    kind,_,opts=items[str(item)]
                    coords=[float(v)/self.scale for v in self.raw.splitlist(self.raw.call(path,'coords',item))]
                    items[str(item)]=(kind,coords,opts)
            return (result,)
        return None

    def rescale(self, scale, work=None):
        geo=self.geometry(self.raw.call('wm','geometry',self.root._w),True)
        match=GEOMETRY.match(str(geo))
        x=int(self.raw.call('winfo','rootx',self.root._w))
        y=int(self.raw.call('winfo','rooty',self.root._w))
        self.scale=scale
        if work:self.work=work
        for name,size in list(self.fonts.items()):
            try:self.raw.call('font','configure',name,'-size',-self.pixels(abs(size)))
            except tk.TclError:pass
        for path,options in list(self.options.items()):
            try:
                if self.raw.call('winfo','exists',path):
                    flat=tuple(v for pair in options.items() for v in pair)
                    self.raw.call(path,'configure',*self.opts(flat,self.kinds[path]))
            except tk.TclError:pass
        for (manager,prefix),options in list(self.layouts.items()):
            try:
                path=prefix[1]
                if self.raw.call('winfo','exists',path) and (prefix[0]!='configure' or self.raw.call('winfo','manager',path)==manager):
                    flat=tuple(v for pair in options.items() for v in pair)
                    self.raw.call(manager,*prefix,*self.opts(flat,'frame' if manager=='place' else ''))
            except tk.TclError:pass
        for path,items in list(self.items.items()):
            for item,(kind,coords,opts) in list(items.items()):
                try:
                    self.raw.call(path,'coords',item,*[float(v)*scale for v in coords])
                    flat=tuple(v for pair in opts.items() for v in pair)
                    if flat:self.raw.call(path,'itemconfigure',item,*self.opts(flat,'frame' if kind=='window' else '',canvas=True))
                except tk.TclError:pass
        if match and match[1]:
            self.raw.call('wm','geometry',self.root._w,f'{self.pixels(match[1])}x{self.pixels(match[2])}{x:+d}{y:+d}')
        self.root.event_generate('<<DpiChanged>>',when='tail')


_original_substitute=tk.Misc._substitute
def _substitute(widget,*args):
    events=_original_substitute(widget,*args)
    if isinstance(widget.tk,LogicalTk):
        for event in events:
            for name in ('x','y','x_root','y_root','width','height'):
                value=getattr(event,name,None)
                if isinstance(value,(float,int)):setattr(event,name,widget.tk.logical(value))
    return events


def attach(root, factor=None, watch=True):
    if isinstance(root.tk,LogicalTk):return root.tk
    dpi,work=monitor(root,root.tk)
    scale=factor if factor is not None else fit_scale(dpi/96,work)
    context=LogicalTk(root,scale,work);root.tk=context
    tk.Misc._substitute=_substitute
    # Tk's named defaults also use explicit native pixels, avoiding mixed units.
    for name in context.raw.splitlist(context.raw.call('font','names')):
        size=int(context.raw.call('font','actual',name,'-size'))
        logical=-abs(size) if size<0 else -round(size*96/72)
        context.fonts[str(name)]=logical
        context.raw.call('font','configure',name,'-size',-context.pixels(abs(logical)))
    if watch and factor is None:
        def poll():
            try:
                dpi,area=monitor(root,context.raw);new=fit_scale(dpi/96,area)
                if abs(new-context.scale)>.01:context.rescale(new,area)
                else:context.work=area
                root.after(750,poll)
            except tk.TclError:pass
        root.after(750,poll)
    return context


def pixels(widget,value):
    return widget.tk.pixels(value) if isinstance(widget.tk,LogicalTk) else int(round(value))
