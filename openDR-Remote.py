
import six

import signal
import socket
import argparse
from datetime import timedelta
from construct import *

import binascii

registers = Struct("registers",
   UBInt16("register"),

   Switch("Register", lambda ctx: ctx.register,
      {
         0x0100: Struct("Data", Enum(UBInt16("Format"),
               BFW_24 = 0,
               BFW_16 = 1,
               WAV_24 = 2,
               WAV_16 = 3,
               MP3_320 = 4,
               MP3_256 = 5,
               MP3_192 = 6,
               MP3_128 = 7,
               MP3_96 = 8,
               _default_ = Pass
               ),
            ),
         0x0101: Struct("Data", Enum(UBInt16("SampleRate"),
                _44_1KHZ = 0,
                _48KHZ = 1,
                _96KHZ = 2,
                _default_ = Pass
                ),
            ),
         0x0108: Struct("Data", Enum(UBInt16("Channels"),
                MONO = 0,
                STEREO = 1,
                _default_ = Pass
                ),
            ),
         0x0109: Struct("Data", Enum(UBInt16("DualFormat"),
               OFF = 0,
               MP3_320 = 1,
               MP3_256 = 2,
               MP3_192 = 3,
               MP3_128 = 4,
               MP3_96 = 5,
               MP3_64 = 6,
               MP3_32 = 7,
               _default_ = Pass
                ),
            ),
      },
      default = Pass,
   )
)

# =====================================================================
# Keep seperate as VU-Meters are very 'talkative'
vumeters = Struct("VUMeters", Padding(1),
   UBInt8("Left-VU"),
   UBInt8("Right-VU"),
   Padding(4),
   SBInt8("Decimal-VU"),
)

updates = Struct("updates",
   Byte("type3"),

   If(lambda ctx: ctx.type3 == 0x12,
      vumeters,
   ),
   If(lambda ctx: ctx.type3 != 0x12,
   Switch("Update", lambda ctx: ctx.type3,
      {
         0x00: Struct("Data", Enum(Byte("Status"),
                        STOPPED = 0x10,
                        PLAYING = 0x11,
                        PLAYPAUSED = 0x12,
                        FORWARD = 0x13,
                        REWIND = 0x14,
                        PAUSED = 0x15,
                        STOPPING = 0x16,
                        RECORD = 0x81,
                        ARMED = 0x82,
                        TIMER = 0x83,
                        _default_ = Pass
                     ),
                     Padding(8),
                 ),
         0x11 : Struct("Data", Padding(1),
                     UBInt32("Counter"),
                     Padding(4),
                 ),
         0x20: Struct("Data", Magic('\x07'),
                     Enum(UBInt8("Scene"),
                        EASY = 0x00,
                        LOUD = 0x01,
                        MUSIC = 0x02,
                        INSTRUMENT = 0x03,
                        INTERVIEW = 0x04,
                        MANUAL = 0x05,
                        DUB = 0x06,
                        PRACTICE = 0x07,
                        _default_ = Pass
                     ),
                 ),
      },
      default = Pass,
   ),
   ),
)

# =====================================================================
file_entry = Struct("Files",
   Peek(BitStruct("Directory",
      Flag("Directory"),
      Padding(7),
   )),
   UBInt16("index"),
   Value("Index", lambda ctx: ctx.index & 0x7fff),
   Padding(8),

   Peek(RepeatUntil(lambda obj, ctx: obj == "\x00\x0d", Field("data",2))),
   Value("flength", lambda ctx: (len(ctx.data) - 1) * 2),
   String("Filename", lambda ctx: ctx.flength, "utf-16-le"),
   Padding(2),
)

file_name = Struct("Filename",
   String("Filename", lambda ctx: ctx._.length - 2, "utf-16-le"),
)

file_data = Struct("FileData",
   Bytes("FileData", lambda ctx: ctx._.length),
)

# =====================================================================
sys_info = Struct("sys_info",
   String("Name", 8),
   Padding(8),
   UBInt16("Version"),
   UBInt16("Build"),
   UBInt16("Wifi1"),
   UBInt16("Wifi2"),
)

# =====================================================================
check_packet = Struct("check_packet",
   Magic("DR"),
   BitStruct("Flags",
      Padding(1),
      Flag("Long"),
      Padding(6),
   ),
   Padding(9),
   UBInt16("length"),
)

short_packet = Struct("short_packet",
   Magic("DR"),
   UBInt16("type"),

   Switch("Type", lambda ctx: ctx.type,
      {
         0x2020 : Embed(updates),
         0x3020 : Embed(registers),
      },
      default = Pass,
   ),
)

long_packet = Struct("long_packet",
   Magic("DR"),
   Peek(UBInt8("type1")),
   BitStruct("Flags",
      Padding(1),
      Flag("Long"),
      Padding(6),
   ),
   UBInt16("type"),

   Padding(7),
   UBInt16("length"),

   Switch("System", lambda ctx: ctx.type,
      {
         0x2000 : sys_info,
         0x2032 : IfThenElse("data", lambda ctx: ctx.type1 == 0xf0,
            file_name,
            file_data,
         ),
         0x2010 : Struct("Files",
            GreedyRange(file_entry),
         ),
      },
      default = Pass,
   ),
)
# =====================================================================
def Run():
   global options
   parser = argparse.ArgumentParser(prog="openDR-Remote")

   # Network Option
   parser.set_defaults(tcp='192.168.1.1', port=8010)
   parser.add_argument("-T", "--tcp", dest="tcp", help="TCP/IP address")
   parser.add_argument("-P", "--port", dest="port", help="TCP/IP port")

   # Perform actions on the recorder
   parser.add_argument("-r", "--reg", action="store_true", dest="reg", help="read registers")
   parser.add_argument("-R", "--rec", action="store_true", dest="rec", help="start recording")
   parser.add_argument("-p", "--play", action="store_true", dest="play", help="start playback")
   parser.add_argument("-s", "--stop", action="store_true", dest="stop", help="stop playback/recording")
   parser.add_argument("-S", "--stream", action="store_true", dest="stream", help="use streaming audio")

   # File actions for device
   parser.add_argument("-l", "--list", action="store_true", dest="listing", help="list stored files")
   parser.add_argument("-d", "--download", dest="download", help="download file [index from listing]")
   options = parser.parse_args()

   if options.download:
      options.listing = True

   s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
   s.connect((options.tcp, int(options.port)))
   s.settimeout(0.001)
   buffer = ""
   loop = 0
   store_file = None

   while True:
      try:
         data = s.recv(14)
         buffer += data
      except socket.timeout:
         pass

      if loop == 0:
         s.send("\x44\x52\x20\x42\x07\x00\x00\x00\x00\x00\x00\x00\x00\x00")

      if options.reg:
         s.send("\x44\x52\xf0\x41\x00\x02\x00\x00\x00\x00\x00\x00\x00\x00") # Request SysInfo

         s.send("\x44\x52\x30\x42\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00") # Read File Type
         s.send("\x44\x52\x30\x42\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00") # Read Sample Rate
         # s.send("\x44\x52\x30\x42\x01\x02\x00\x00\x00\x00\x00\x00\x00\x00")
         # s.send("\x44\x52\x30\x42\x01\x03\x00\x00\x00\x00\x00\x00\x00\x00")
         # s.send("\x44\x52\x30\x42\x01\x04\x00\x00\x00\x00\x00\x00\x00\x00")
         # s.send("\x44\x52\x30\x42\x01\x05\x00\x00\x00\x00\x00\x00\x00\x00")
         # s.send("\x44\x52\x30\x42\x01\x06\x00\x00\x00\x00\x00\x00\x00\x00")
         # s.send("\x44\x52\x30\x42\x01\x07\x00\x00\x00\x00\x00\x00\x00\x00")
         s.send("\x44\x52\x30\x42\x01\x08\x00\x00\x00\x00\x00\x00\x00\x00") # Read Channels
         s.send("\x44\x52\x30\x42\x01\x09\x00\x00\x00\x00\x00\x00\x00\x00") # Read Dual Mode

         # s.send("\x44\x52\x30\x42\x02\x00\x00\x00\x00\x00\x00\x00\x00\x00")
         # s.send("\x44\x52\x30\x42\x02\x01\x00\x00\x00\x00\x00\x00\x00\x00")
         # s.send("\x44\x52\x30\x42\x02\x05\x00\x00\x00\x00\x00\x00\x00\x00")
         # s.send("\x44\x52\x30\x42\x02\x02\x00\x00\x00\x00\x00\x00\x00\x00")
         # s.send("\x44\x52\x30\x42\x02\x03\x00\x00\x00\x00\x00\x00\x00\x00")
         # s.send("\x44\x52\x30\x42\x02\x04\x00\x00\x00\x00\x00\x00\x00\x00")

         # s.send("\x44\x52\x30\x42\x0b\x00\x00\x00\x00\x00\x00\x00\x00\x00")
         # s.send("\x44\x52\x30\x42\x0a\x80\x00\x00\x00\x00\x00\x00\x00\x00")

         s.send("\x44\x52\xf0\x41\x32\x00\x00\x00\x00\x00\x00\x00\x00\x00") # Request Filename + Device Name
         s.send("\x44\x52\x20\x42\x11\x00\x00\x00\x00\x00\x00\x00\x00\x00") # Read Counter
         s.send("\x44\x52\x20\x42\x20\x07\x00\x00\x00\x00\x00\x00\x00\x00") # Read Scene
         s.send("\x44\x52\x20\x42\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00") # Read Status
         options.reg = False

      if (options.stream):
         s.send("\x44\x52\xf0\x41\x21\x01\x00\x00\x00\x00\x00\x00\x00\x00")
         options.stream= False

      if (options.play):
         s.send("\x44\x52\x10\x41\x00\x09\x00\x00\x00\x00\x00\x00\x00\x00") # Press "Play"
         options.play = False

      if (options.rec):
         s.send("\x44\x52\x10\x41\x00\x0b\x00\x00\x00\x00\x00\x00\x00\x00") # Press "Record"
         options.rec = False

      if (options.stop):
         s.send("\x44\x52\x10\x41\x00\x08\x00\x00\x00\x00\x00\x00\x00\x00") # Press "Stop"
         options.stop= False

      if options.listing:
         s.send("\x44\x52\x40\x41\x10\x00\x00\x00\x00\x00\x00\x00\x00\x00")
         options.listing = False

      if (len(buffer) >= 14):
         try:
            # ensure that there is enough data
            log = check_packet.parse(buffer)

            if log.Flags.Long:
               if log.length:
                  try:
                     data = s.recv(log.length)
                     buffer += data
                  except socket.timeout:
                     pass

               if (len(buffer) >= log.length + 14):
                  #print "Buf:", binascii.hexlify(buffer[:14]), "...", log.length
                  log = long_packet.parse(buffer)
                  buffer = buffer[log.length + 14:]
               else:
                  log = None
            else:
               #print "Buf:", binascii.hexlify(buffer[:14])
               log = short_packet.parse(buffer)
               buffer = buffer[14:]
         except ConstError:
            # magic not found
            buffer = ""
            log = None
      else:
         log = None

      loop = loop + 1

      if log:
         if log.get('Update'):
            print log.Update
         if log.get('Register'):
            print log.Register
         if log.get('System'):
            if log.System.get('Files'):
               for x in range(len(log.System.Files)):
                  if options.download:
                     if int(options.download) == log.System.Files[x].Index:
                        storage_file = open(log.System.Files[x].Filename, "wb")
                        s.send("\x44\x52\x40\x41\x30\x00\x00"+chr(int(options.download))+"\x00\x00\x00\x00\x00\x00")
                        print "*",
                  print log.System.Files[x].Index, "=", log.System.Files[x].Filename
            elif log.System.get('FileData') and storage_file:
               storage_file.write(log.System.FileData)
            else:
               print log.System

if __name__ == '__main__':
   Run()
