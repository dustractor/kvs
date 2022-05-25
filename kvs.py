import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk as g
from gi.repository import Gio
from gi.repository import Gdk
from sqlite3 import connect,Connection
from pathlib import Path
from os import walk
from os.path import join
from locale import getpreferredencoding as enc
from re import compile as re
from argparse import ArgumentParser

args = ArgumentParser()
args.add_argument("--key")
args.add_argument("--value")

argument_namespace,fakeargv = args.parse_known_args()
globals().update(argument_namespace.__dict__)

CONFIG_PATH = Path.home() / ".config" / "kvs"
if not CONFIG_PATH.is_dir() and CONFIG_PATH.parent.is_dir():
    print("making config path")
    CONFIG_PATH.mkdir()
DB_NAME = str(Path.home() / ".config" / "kvs"/ "kvs_2.sdlitedb") 
print("DB_NAME:",DB_NAME)

# {{{1 define and connect to a database

# {{{2 sql

schema =  """

create table if not exists kvs (
id integer primary key,
key text,
val text,
unique(key) on conflict replace);

"""

# }}}2

# {{{2 class

class Db(Connection):
    def __init__(self,name,**kwargs):
        super().__init__(name,**kwargs)
        self.cu = self.cursor()
        self.cu.row_factory = lambda c,r:r[0]
        made = bool(self.cu.execute("select * from sqlite_master").fetchone())
        if not made:
            print("making",DB_NAME)
            self.executescript(schema)
            self.commit()

# }}}2

cx = connect(DB_NAME,factory=Db)

# }}}1

def files_in_path_recursive(path):
    for r,ds,fs in walk(str(path)):
        for ff in fs:
            yield Path(join(r,ff))

def files_in_selection(selection):
    is_uri = re("file://").match
    for p in (Path(f).resolve()
              for f in (u[7:]
                  for u in filter(is_uri,
            selection.get_data().decode(
                encoding=enc()
                ).splitlines()))):
        if p.is_dir():
            yield from files_in_path_recursive(p)
        elif p.is_file():
            yield p


class Win(g.ApplicationWindow):

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.sel_idx = -1
        self.iter_x = None
        store = g.ListStore(int,str,str)
        self.toolbar = g.Toolbar()
        icn = g.Image.new_from_file("/usr/share/icons/hicolor/32x32/actions/albumfolder-new.png")
        self.toolbtn1 = g.ToolButton(icon_widget=icn,label="add")
        self.toolbtn1.connect("clicked",self.toolbtn1_clicked)
        self.toolbtn1.set_tooltip_text("foo bar baz")
        self.toolbar.insert(self.toolbtn1,-1)
        self.box = g.Box(orientation=1,spacing=10)
        self.box.set_border_width(24)
        self.box.add(self.toolbar)
        self.add(self.box)
        builder = g.Builder.new_from_file("chk.glade")
        self.chk1 = builder.get_object("recursive_add")
        self.chk1.connect("toggled",self.chk_toggle)
        self.box.add(self.chk1)
        self.listframe = g.Frame()
        self.listframe.set_label("baz")
        self.box.add(self.listframe)
        scroll_tree = g.ScrolledWindow()
        scroll_tree.set_vexpand(True)
        self.listframe.add(scroll_tree)
        self.tree_list = g.TreeView(model=store)
        self.tree_list.set_border_width(3)
        self.tree_list.connect("row-activated",self.row_activation_upd)
        self.tree_list.get_selection().connect("changed",self.row_selection_changed)
        scroll_tree.add(self.tree_list)
        for i,t in enumerate("id key val".split()):
            ren = g.CellRendererText()
            col = g.TreeViewColumn(t,ren,text=i)
            self.tree_list.append_column(col)
        self.inspectframe = g.Frame()
        self.box.add(self.inspectframe)
        self.inspectframe.set_border_width(10)
        inspectframebox = g.Box(orientation=1,spacing=10)
        self.inspectframe.add(inspectframebox)
        self.inspectlabel = g.Label()
        self.inspectentry = g.Entry()
        self.inspectentry.connect("activate",self.entry_func)
        inspectframebox.add(self.inspectlabel)
        inspectframebox.add(self.inspectentry)
        button = g.Button()
        button.set_label("delete")
        button.set_margin_start(20)
        button.set_can_focus(False)
        button.connect("clicked",self.delete_selected)
        button.set_margin_end(20)
        self.box.add(button)
        self.ximg = g.Image.new_from_file("/usr/share/icons/hicolor/32x32/apps/org.xfce.terminalemulator.png")
        self.ximgbtn = g.Button()
        self.ximgbtn.set_image(self.ximg)
        self.ximgbtn.connect("clicked",self.ximgbtn_click)
        self.box.add(self.ximgbtn)
        self.connect("drag-motion",self.drag_motion)
        self.connect("drag-data-received",self.receive_dropped_uris)
        self.drag_dest_set(
            g.DestDefaults.MOTION|g.DestDefaults.HIGHLIGHT|g.DestDefaults.DROP,
            [g.TargetEntry.new("text/uri-list", 0, 80)], Gdk.DragAction.COPY)
        self.set_default_size(1024,768)
        self.refresh_store()
        self.show_all()

    def refresh_store(self):
        store = self.tree_list.get_model()
        store.clear()
        for oid,key,val in cx.execute(
                "select id,key,val from kvs"):
            store.append([oid,key,val])

    def add_files_as_keys(self,filelist):
        print("filelist:",filelist)
        store = self.tree_list.get_model()
        for p in filelist:
            key = str(p)
            val = p.name
            rowid = cx.execute(
                "insert into kvs (key,val) values (?,?)",
                (key,val)).lastrowid
            print("rowid:",rowid)
        cx.commit()
        self.refresh_store()

    def drag_motion(self,widget,context,x,y,timestamp):
        self.listframe.drag_highlight()
        self.listframe.queue_draw()
        return True

    def receive_dropped_uris(self,widget,context,x,y,selection,target_type,timestamp):
        files = list(files_in_selection(selection))
        self.add_files_as_keys(files)
        self.listframe.drag_unhighlight()
        self.listframe.queue_draw()
        context.finish(True,False,timestamp)

    def row_selection_changed(self,treesel):
        store,iterx = treesel.get_selected()
        if not iterx:
            return
        oid,key,val = (
            store.get_value(iterx,0),
            store.get_value(iterx,1),
            store.get_value(iterx,2))
        self.sel_idx = oid
        self.inspectframe.set_label(key)
        self.inspectlabel.set_label(val)
        self.inspectentry.set_text(val)
        self.iter_x = iterx

    def delete_selected(self,button):
        sel = self.tree_list.get_selection()
        store,iterx = sel.get_selected()
        if not iterx:
            return
        oid = store.get_value(iterx,0)
        cx.execute("delete from kvs where id=?",(oid,))
        cx.commit()
        print("removed oid:",oid)
        store.remove(iterx)
        self.iterx = None

    def entry_func(self,entry):
        if (self.sel_idx > -1) and self.iter_x:
            txt = entry.get_text()
            cx.execute(
                "update kvs set val=? where id=?",
                (txt,self.sel_idx))
            cx.commit()
            store = self.tree_list.get_model()
            store.set_value(self.iter_x,2,txt)
            self.inspectlabel.set_label(txt)
            self.tree_list.grab_focus()

    def row_activation_upd(self,*args):
        self.inspectentry.grab_focus()

    def ximgbtn_click(self,*args):
        print("args:",args)

    def toolbtn1_clicked(self,*args):
        print("args:",args)
        dialog = g.FileChooserDialog(
            title="foo",
            action=g.FileChooserAction.SELECT_FOLDER)
        dialog.add_buttons(
            g.STOCK_CANCEL,g.ResponseType.CANCEL,
            "Select",g.ResponseType.OK)
        response = dialog.run()
        if response == g.ResponseType.OK:
            foldername = dialog.get_filename()
            path = Path(foldername)
            self.add_files_as_keys(list(files_in_path_recursive(path)))
        dialog.destroy()

    def chk_toggle(self,checkbutton):
        print("checkbutton:",checkbutton)
        print("checkbutton.get_active():",checkbutton.get_active())



class App(g.Application):

    def on_quit(self,action,param):
        self.quit()

    def on_info(self,action,param):
        list(map(print,cx.iterdump()))
        self.about.show()

    def dialog_response(self,dialog,response):
        print("dialog:",dialog)
        print("response:",response)
        dialog.hide()

    def on_folder_open(self,action,param):
        print("self,action,param:",self,action,param)
        dialog = g.FileChooserDialog(
            title="foo",
            action=g.FileChooserAction.SELECT_FOLDER)
        dialog.add_buttons(
            g.STOCK_CANCEL,g.ResponseType.CANCEL,
            "Select",g.ResponseType.OK)
        response = dialog.run()
        if response == g.ResponseType.OK:
            foldername = dialog.get_filename()
            path = Path(foldername)
            self.window.add_files_as_keys(list(files_in_path_recursive(path)))
        dialog.destroy()

    def do_startup(self):
        g.Application.do_startup(self)
        actiondata = (
            ("quit",self.on_quit),
            ("info",self.on_info),
            ("folderopen",self.on_folder_open))
        for name,callback in actiondata:
            action = Gio.SimpleAction.new(name,None)
            action.connect("activate",callback)
            self.add_action(action)
        builder = g.Builder.new_from_file("appmenu.xml")
        self.set_app_menu(builder.get_object("app-menu"))
        builder = g.Builder.new_from_file("menu.xml")
        self.set_menubar(builder.get_object("menu"))
        self.about = g.AboutDialog()
        self.about.connect("response",self.dialog_response)
        print("...",end="")

    def do_activate(self):
        self.window = Win(application=self,title="Hello World!")
        print("<",end="")
        self.window.present()
        print("/>")


app = App(application_id="org.dust.hello_9001")

app.run(fakeargv)

