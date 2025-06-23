**Modbus Simulator**

A Python-based Modbus RTU/TCP simulator with a graphical user interface (GUI) for defining and mapping registers and coils. 

**Supports:**

- Modbus TCP slave (function codes 1–4)

- Modbus RTU slave (serial) with pyserial

- Data types: Boolean, 16‑bit signed/unsigned integer, 32‑bit float (configurable byte order)

- Randomized simulation within user‑defined value ranges

- Import/export of register maps via CSV

- Start/Stop toggle for both TCP and RTU modes

- Editable entries via double‑click dialog

**Features**

- GUI configuration: Add, edit, and remove map entries via form and treeview.

- CSV I/O: Save your map to a CSV file or load an existing one (Function,Address,Data Type,Byte Order,No.Addresses,Value From,Value To).

- Protocol modes: Switch between TCP and RTU slaves; irrelevant settings disable automatically.

- Start/Stop server: Cleanly launch or stop your chosen server without restarting the app.

- Byte order: Supports 1234, 2143, 3412, 4321 for splitting floats into two 16‑bit registers.

**Requirements**
- Python 3.7+
- tkinter
- pyserial for RTU support

**Installation**

python -m venv venv
source venv/bin/activate   # Linux/macOS
venv\\Scripts\\activate  # Windows

Install dependencies:

pip install pyserial  # only if you need RTU support

**Usage**

Run the simulator with default TCP port 502:

- python ModbusTCPEmulator.py

Command‑line options

--host: TCP bind address (default 0.0.0.0)

--tcp-port: TCP port (default 502)

--serial-port: Serial device for RTU mode (e.g. COM3 or /dev/ttyUSB0)

--baudrate: Baud rate for RTU (default 9600)

--unit-id: Modbus slave ID (default 1)

Configuring registers

Use Mode selector to pick TCP or RTU.

Enter Host/Port or Serial/Baud settings.

In New Entry, choose Function (01–04), Address (auto‑defaults to 1, 10001, 40001, 30001), Data Type, Byte Order, number of registers, and value range.

Click Add to insert into the table below; double‑click any row to edit.

Import/Export your map via the File ▶ Import/Export CSV menu.

**Running the server**

Click Start to launch the selected slave.

Click Stop to terminate all client connections and stop listening.

CSV Format Example
