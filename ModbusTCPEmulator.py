import socket
import threading
import struct
import csv
import random
import argparse
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# CSV fields for import/export
CSV_FIELDS = ['Function', 'Address', 'Data Type', 'Byte Order', 'No.Addresses', 'Value From', 'Value To']

# Optional: for RTU serial support, install pyserial
try:
    import serial
except ImportError:
    serial = None

# CRC16 (Modbus) implementation
def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 0x0001:
                crc >>= 1
                crc ^= 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF

# Pack values for coils or registers
def pack_value(val, dtype, order=None):
    if dtype == 'Boolean':
        return 1 if val else 0
    if 'float' in dtype.lower():
        raw = struct.pack('>f', val)
        b = list(raw)
        if order == '1234': return [(b[0]<<8)|b[1], (b[2]<<8)|b[3]]
        if order == '2143': return [(b[1]<<8)|b[0], (b[3]<<8)|b[2]]
        if order == '3412': return [(b[2]<<8)|b[3], (b[0]<<8)|b[1]]
        if order == '4321': return [(b[3]<<8)|b[2], (b[1]<<8)|b[0]]
        raise ValueError(f"Unknown byte order: {order}")
    if 'signed' in dtype.lower():
        i = int(val) & 0xFFFF
        return [i]
    if 'unsigned' in dtype.lower():
        return [int(val) & 0xFFFF]
    raise ValueError(f"Unsupported data type: {dtype}")

# Simulation engine
def simulate(entries, func, start, count):
    results = []
    for i in range(count):
        addr = start + i
        entry = next((e for e in entries if e['func']==func and addr>=e['offset'] and addr<e['offset']+e.get('num',1)), None)
        if entry:
            if entry['dtype'] == 'Boolean':
                results.append(random.choice([0,1]))
            else:
                val = random.uniform(entry['vmin'], entry['vmax'])
                words = pack_value(val, entry['dtype'], entry['order'])
                results.append(words[addr - entry['offset']])
        else:
            results.append(0)
    return results

# Modbus TCP handler
def handle_tcp(conn, entries, unit_id):
    try:
        while True:
            hdr = conn.recv(7)
            if len(hdr) < 7: break
            tid, pid, length, uid = struct.unpack('>HHHB', hdr)
            pdu = conn.recv(length - 1)
            func = pdu[0]
            start, qty = struct.unpack('>HH', pdu[1:5])
            if func in (1,2):
                bits = simulate(entries, f"{func:02d}", start, qty)
                bc = (qty+7)//8; data = bytearray(bc)
                for i,b in enumerate(bits):
                    if b: data[i//8] |= 1<<(i%8)
                resp_pdu = struct.pack('>BB', func, bc) + data
            elif func in (3,4):
                regs = simulate(entries, f"{func:02d}", start, qty)
                resp_pdu = struct.pack('>BB', func, len(regs)*2)
                for r in regs: resp_pdu += struct.pack('>H', r)
            else:
                break
            mbap = struct.pack('>HHHB', tid, 0, len(resp_pdu)+1, uid)
            conn.sendall(mbap + resp_pdu)
    except:
        pass

# Modbus TCP server
def tcp_server(host, port, entries, unit_id=1, running_flag=None):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port)); sock.listen(5)
    while running_flag and running_flag.is_set():
        try:
            sock.settimeout(1.0)
            conn, _ = sock.accept()
            threading.Thread(target=handle_tcp, args=(conn, entries, unit_id), daemon=True).start()
        except socket.timeout:
            continue
        except OSError:
            break
    sock.close()

# Modbus RTU handler
def handle_rtu(frame, ser, entries, unit_id):
    if frame[0] != unit_id: return
    func = frame[1]; start, qty = struct.unpack('>HH', frame[2:6])
    if func in (1,2):
        bits = simulate(entries, f"{func:02d}", start, qty)
        bc = (qty+7)//8; data = bytearray(bc)
        for i,b in enumerate(bits):
            if b: data[i//8] |= 1<<(i%8)
        resp = bytearray([unit_id, func, bc]) + data
    elif func in (3,4):
        regs = simulate(entries, f"{func:02d}", start, qty)
        resp = bytearray([unit_id, func, len(regs)*2])
        for r in regs: resp += struct.pack('>H', r)
    else:
        return
    c = crc16(resp); resp += struct.pack('<H', c)
    ser.write(resp)

# Modbus RTU server
def rtu_server(port, baud, entries, unit_id=1, running_flag=None):
    if not serial:
        messagebox.showerror('Error', 'pyserial not installed')
        return
    ser = serial.Serial(port, baudrate=baud, timeout=0.1)
    buf = bytearray()
    while running_flag and running_flag.is_set():
        b = ser.read(1)
        if not b: continue
        buf += b
        if len(buf) < 8: continue
        for i in range(8, len(buf)+1):
            frame = bytes(buf[:i]); rc = frame[-2] | (frame[-1]<<8)
            if crc16(frame[:-2]) == rc:
                handle_rtu(frame, ser, entries, unit_id)
                buf = buf[i:]
                break
    ser.close()

# CSV import/export
def import_csv(entries, tree):
    path = filedialog.askopenfilename(filetypes=[('CSV files','*.csv')])
    if not path: return
    with open(path, newline='') as f:
        rd = csv.DictReader(f); entries.clear(); tree.delete(*tree.get_children())
        for r in rd:
            func=r['Function']; addr=int(r['Address'])
            base={'01':0,'02':10000,'03':40000,'04':30000}[func]
            off=addr-base-1
            e={'func':func,'offset':off,'dtype':r['Data Type'],'order':r.get('Byte Order','') or '1234',
               'num':int(r['No.Addresses']),'vmin':float(r['Value From']),'vmax':float(r['Value To'])}
            entries.append(e)
            tree.insert('', 'end', values=(func, addr, e['dtype'], e['order'], e['num'], e['vmin'], e['vmax']))
def export_csv(entries):
    path = filedialog.asksaveasfilename(defaultextension='.csv', filetypes=[('CSV files','*.csv')])
    if not path: return
    with open(path, 'w', newline='') as f:
        w = csv.writer(f); w.writerow(CSV_FIELDS)
        for e in entries:
            base={'01':0,'02':10000,'03':40000,'04':30000}[e['func']]
            addr = base + e['offset'] + 1
            w.writerow([e['func'], addr, e['dtype'], e['order'], e['num'], e['vmin'], e['vmax']])

# Launch GUI
def launch_gui(entries, args):
    root = tk.Tk(); root.title('Modbus Simulator')
    root.protocol('WM_DELETE_WINDOW', root.quit)
    
    # Menu
    menubar = tk.Menu(root); filem = tk.Menu(menubar, tearoff=0)
    filem.add_command(label='Import CSV', command=lambda: import_csv(entries, tree))
    filem.add_command(label='Export CSV', command=lambda: export_csv(entries))
    filem.add_separator(); filem.add_command(label='Exit', command=root.quit)
    menubar.add_cascade(label='File', menu=filem); root.config(menu=menubar)
    
    main = ttk.Frame(root, padding=10); main.grid(row=0, column=0, sticky='nsew')
    root.rowconfigure(0, weight=1); root.columnconfigure(0, weight=1)

    # Mode selection
    mode_var = tk.StringVar(value='TCP')
    mf = ttk.Labelframe(main, text='Mode'); mf.grid(row=0, column=0, sticky='w')
    ttk.Radiobutton(mf, text='TCP', variable=mode_var, value='TCP').grid(row=0, column=0)
    ttk.Radiobutton(mf, text='RTU', variable=mode_var, value='RTU').grid(row=0, column=1)

    # Server settings
    ss = ttk.Labelframe(main, text='Server Settings'); ss.grid(row=1, column=0, sticky='w')
    host_var = tk.StringVar(value=args.host); port_var = tk.StringVar(value=str(args.tcp_port))
    serial_var = tk.StringVar(value=args.serial_port or ''); baud_var = tk.StringVar(value=str(args.baudrate))
    ttk.Label(ss, text='Host').grid(row=0, column=0)
    host_entry = ttk.Entry(ss, textvariable=host_var); host_entry.grid(row=0, column=1)
    ttk.Label(ss, text='Port').grid(row=1, column=0)
    port_entry = ttk.Entry(ss, textvariable=port_var); port_entry.grid(row=1, column=1)
    ttk.Label(ss, text='Serial').grid(row=2, column=0)
    serial_entry = ttk.Entry(ss, textvariable=serial_var); serial_entry.grid(row=2, column=1)
    ttk.Label(ss, text='Baud').grid(row=3, column=0)
    baud_entry = ttk.Entry(ss, textvariable=baud_var); baud_entry.grid(row=3, column=1)

    # Toggle enable/disable based on mode
    def toggle_mode(*_):
        if mode_var.get() == 'TCP':
            host_entry.config(state='normal'); port_entry.config(state='normal')
            serial_entry.config(state='disabled'); baud_entry.config(state='disabled')
        else:
            host_entry.config(state='disabled'); port_entry.config(state='disabled')
            serial_entry.config(state='normal'); baud_entry.config(state='normal')
    mode_var.trace_add('write', toggle_mode)
    toggle_mode()

    # Entry Form
    form = ttk.Labelframe(main, text='New Entry', padding=10); form.grid(row=2, column=0, sticky='nw')
    func_var = tk.StringVar(value='03')
    ttk.Label(form, text='Function').grid(row=0, column=0)
    func_cb = ttk.Combobox(form, textvariable=func_var, values=['01','02','03','04'], state='readonly'); func_cb.grid(row=0, column=1)
    fields = ['Address','Data Type','Byte Order','No.Addresses','Value From','Value To']
    vars_f = {}
    for i, f in enumerate(fields,1):
        ttk.Label(form, text=f).grid(row=i, column=0)
        var = tk.StringVar(); vars_f[f] = var
        if f == 'Data Type':
            data_cb = ttk.Combobox(form, textvariable=var, state='readonly'); data_cb.grid(row=i, column=1)
        elif f == 'Byte Order':
            var.set('1234'); ttk.Combobox(form, textvariable=var, values=['1234','2143','3412','4321'],state='readonly').grid(row=i, column=1)
        else:
            ttk.Entry(form, textvariable=var).grid(row=i, column=1)
    def update_types(*_):
        f = func_var.get()
        if f in('01','02'):
            data_cb.config(values=['Boolean']); vars_f['Data Type'].set('Boolean')
        else:
            data_cb.config(values=['32-bit float','16-bit signed integer','16-bit unsigned integer']); vars_f['Data Type'].set('32-bit float')
        defaults = {'01':'1','02':'10001','03':'40001','04':'30001'}
        vars_f['Address'].set(defaults[f])
    func_cb.bind('<<ComboboxSelected>>', update_types); update_types()
    vars_f['Data Type'].trace_add('write', lambda *_: vars_f['No.Addresses'].set('2' if vars_f['Data Type'].get()=='32-bit float' else '1'))
    def add_entry():
        try:
            func = func_var.get(); addr=int(vars_f['Address'].get()); dtype=vars_f['Data Type'].get()
            order=vars_f['Byte Order'].get(); num=int(vars_f['No.Addresses'].get())
            vmin=float(vars_f['Value From'].get()); vmax=float(vars_f['Value To'].get())
            base = {'01':0,'02':10000,'03':40000,'04':30000}[func]; off=addr-base-1
            e={'func':func,'offset':off,'dtype':dtype,'order':order,'num':num,'vmin':vmin,'vmax':vmax}
            entries.append(e); tree.insert('','end',values=(func,addr,dtype,order,num,vmin,vmax))
        except Exception as ex: messagebox.showerror('Invalid Entry', str(ex))
    ttk.Button(form, text='Add', command=add_entry).grid(row=len(fields)+1, column=0, columnspan=2, pady=5)

    # Treeview
    cols = ['Function','Address','Type','Order','Regs','Min','Max']
    tree = ttk.Treeview(main, columns=cols, show='headings')
    for c in cols: tree.heading(c, text=c); tree.column(c, width=80)
    tree.grid(row=3, column=0, sticky='nsew', pady=10)
    main.rowconfigure(3, weight=1); main.columnconfigure(0, weight=1)

    # Edit on double-click
    def edit_entry(event):
        sel = tree.selection();
        if not sel: return
        idx = tree.index(sel[0]); e = entries[idx]
        dlg = tk.Toplevel(root); dlg.title('Edit Entry')
        labs = ['Function','Address','Data Type','Byte Order','No.Addresses','Value From','Value To']
        edit_vars = {}
        for i, lab in enumerate(labs):
            ttk.Label(dlg, text=lab).grid(row=i, column=0)
            var = tk.StringVar(); edit_vars[lab]=var
            if lab=='Function':
                cb=ttk.Combobox(dlg,textvariable=var,values=['01','02','03','04'],state='readonly'); cb.grid(row=i,column=1); cb.set(e['func'])
            elif lab=='Address':
                base={'01':0,'02':0,'03':1,'04':1}[e['func']]; var.set(str(e['offset']+base)); ttk.Entry(dlg,textvariable=var).grid(row=i,column=1)
            elif lab=='Data Type':
                cb=ttk.Combobox(dlg,textvariable=var,state='readonly'); cb.grid(row=i,column=1)
                vals=['Boolean'] if e['func'] in('01','02') else ['32-bit float','16-bit signed integer','16-bit unsigned integer']
                cb.config(values=vals); cb.set(e['dtype'])
            elif lab=='Byte Order':
                cb=ttk.Combobox(dlg,textvariable=var,values=['1234','2143','3412','4321'],state='readonly'); cb.grid(row=i,column=1); cb.set(e['order'])
            else:
                ttk.Entry(dlg,textvariable=var).grid(row=i,column=1)
                if lab=='No.Addresses': var.set(str(e.get('num',1)))
                elif lab=='Value From': var.set(str(e['vmin']))
                elif lab=='Value To': var.set(str(e['vmax']))
        def save_edit():
            e['func']=edit_vars['Function'].get()
            addr=int(edit_vars['Address'].get()); base={'01':0,'02':0,'03':1,'04':1}[e['func']]
            e['offset']=addr-base; e['dtype']=edit_vars['Data Type'].get(); e['order']=edit_vars['Byte Order'].get()
            e['num']=int(edit_vars['No.Addresses'].get()); e['vmin']=float(edit_vars['Value From'].get()); e['vmax']=float(edit_vars['Value To'].get())
            tree.item(sel[0], values=(e['func'], addr, e['dtype'], e['order'], e['num'], e['vmin'], e['vmax']))
            dlg.destroy()
        ttk.Button(dlg, text='Save', command=save_edit).grid(row=len(labs), column=0, columnspan=2)
    tree.bind('<Double-1>', edit_entry)

    # Start/Stop controls
    ctrl = ttk.Frame(root, padding=10)
    ctrl.grid(row=4, column=0, sticky='w')

    running_flag = threading.Event()
    conns = []

    # Wrap handle_tcp to track and close connections
    def handle_tcp_wrapper(conn):
        try:
            handle_tcp(conn, entries, args.unit_id)
        finally:
            try:
                conn.close()
            except:
                pass
            if conn in conns:
                conns.remove(conn)

    def server_loop():
        if mode_var.get() == 'TCP':
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((host_var.get(), int(port_var.get())))
            sock.listen(5)
            while running_flag.is_set():
                try:
                    sock.settimeout(1.0)
                    conn, _ = sock.accept()
                    conns.append(conn)
                    threading.Thread(target=handle_tcp_wrapper, args=(conn,), daemon=True).start()
                except socket.timeout:
                    continue
                except OSError:
                    break
            sock.close()
            # Close all open client connections
            for c in conns:
                try:
                    c.close()
                except:
                    pass
            conns.clear()
        else:
            # RTU server runs until running_flag is cleared
            if not serial:
                messagebox.showerror('Error', 'pyserial not installed')
                running_flag.clear()
                return
            ser = serial.Serial(serial_var.get(), baudrate=int(baud_var.get()), timeout=0.1)
            while running_flag.is_set():
                b = ser.read(1)
                if not b:
                    continue
                frame_buf = bytearray(b)
                # accumulate until full frame and process
                # reuse existing rtu_server logic with running_flag
            ser.close()

    def toggle_server():
        if not running_flag.is_set():
            running_flag.set()
            start_btn.config(text='Stop')
            toggle_mode()
            threading.Thread(target=server_loop, daemon=True).start()
        else:
            running_flag.clear()
            start_btn.config(text='Start')

    start_btn = ttk.Button(ctrl, text='Start', command=toggle_server)
    start_btn.grid(row=0, column=0)

    root.mainloop()()

if __name__=='__main__':
    parser = argparse.ArgumentParser(description='Modbus Simulator')
    parser.add_argument('--tcp-port', type=int, default=502)
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--serial-port')
    parser.add_argument('--baudrate', type=int, default=9600)
    parser.add_argument('--unit-id', type=int, default=1)
    args = parser.parse_args()
    entries = []
    launch_gui(entries, args)
