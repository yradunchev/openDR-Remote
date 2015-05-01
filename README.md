OpenDR-Remote
=============

This project was started in response to the lack of Linux support
for the DR-22WL audio record, and lack of a public API. The project
aims to reverse engineer the network protocol that is used to control
the recorder and demostrate how the protocol can be used.

The reverse engineering is being done at the network layer, using 
wireshark on a rooted Android device.

The Hardware
============

The audio recorder is a high quality wav/mp3 recorder, with WiFi capabilities
provided by a GainSpan micro. The device acts as a WiFi AP and issues the
connecting PC with 192.168.1.22 (using 192.168.1.1 for itself).

All control is done through a TCP/IP connection to port 8010.

I own a DR-22WL, there is also a DR-44WL (4 channel) recorder which is
known to use the same/similar protocol. If anyone wants to provide logs
from one of those we could analyse the differences.

Packets
=======

Construction:
* All packets start with 0x44, 0x52 ("DR") and are nominally 14 bytes long.
* Packets are padded with 0x00 upto complete size.
* If the 3rd byte is 0xF0 it is an extended packet and the additional number
  of bytes is in the 13th+14th byte. (...:05:68 = 0x0568 = 1384, add 14 to
  give 1398 byte packet)
* Some TCP/IP packets contain multiple Tascam packets, this may just be an
  articfact of wireshark. None the less they seem to be treated same as
  seperate packets.

Packets are either 'status' which are automatically issued (for display 
updates/streaming audio/etc), or 'command/response' pairs. There are some 
pcap files in the 'pcap' directory and annotated text files explaining 
them.

$ tshark -r shark_dump_1430448755.pcap -Tfields -e frame.number  -e ip.src
 -e ip.dst -e tcp.len -e data.data > shark_dump_1430448755.pcap.txt

Display/Status updates (recorder -> computer)
--
These are 14 bytes starting "44:52:20:20:"

VU Meters:
44:52:20:20:12:00:02:02:00:00:00:00:d3:10
                  LL RR                    VU meter L/R values (00..0f, and 85..8f seen) 
                                    NN     possibly numeric value show in top-right of app
                                           (7f..ff seen)

Time Counter:
44:52:20:20:11:01:00:00:00:11:00:00:4c:f5
                  ?? ?? SS SS              decimal seconds counter

Status Indicator:
44:52:20:20:00:82:00:00:00:00:00:00:00:00
               RR                          10=Stopped, 82=Record+Pause, 81=Record, 12, 16
                                           10=Stopped, 11=Play, 15
Dial Mode:
44:52:20:20:20:07:05:00:00:00:00:00:00:00
                  DD                       00=Easy, 01=Loud, 02=Music, 03=Instrument, 04=Interview, 05=Manual

LowCut/LevelControl:
44:52:f0:20:31:00:00:00:00:00:00:00:00:14:00:00:00:00:00:01:00:01:00:00:00:00:00:00:00:01:00:02:00:00
                                                         XX         00=Off, 01=40Hz, 02=80Hz, 03=120Hz, 04=220Hz
                                                               XX   00=Off, 01=Limiter, 02=Peak, 03=Auto (only on interview)

Streamed Audio (recorder -> computer)
--
These are like updates in that they are sent automatically, but obviously a
lot larger. No analysis (yet) on what they contain.

44:52:f0:20:20:01:10:00:00:20:2b:00:05:68:00:00:00:00:.... 
                                    ++ ++ (extra size :05:68 for total of 1398 bytes per packet)


Command/Response
--

Request Configuration Setting:
C > 44:52:30:42:01:01:00:00:00:00:00:00:00:00 (register '01:01')
R < 44:52:30:20:01:01:00:01:00:00:00:00:00:00
                rr rr    vv 
--
response for '01:00' = '00' is BWF24, '01' is BFW16, '02' is Wav24, '04'=MP3-320
response for '01:01' = '00' is 44.1KHz, '01' is 48KHz, '02' is 96KHz

'01:00'...'01:09','02:00'...'02:07' requested by app on connect
--


Request Current Filename:
C > 44:52:f0:41:32:00:00:00:00:00:00:00:00:00
R < 44:52:f0:20:32:00:00:01:00:00:00:00:00:20:31:00:35:00:30:00:34:00:32:00:39:00:5f:00:30:00:30:00:33:00:33:00:2e:00:77:00:61:00:76:00:00:00
                                              ++    ++    ++    ++    ++    ++    ++    ++    ++    ++    ++    ++    ++    ++    ++    ??
--
In unicode?
$ echo -n '150429_0033.wav' | hexdump -C
00000000  31 35 30 34 32 39 5f 30  30 33 33 2e 77 61 76     |150429_0033.wav|
--

Request Device Version:
C > 44:52:f0:41:00:02:00:00:00:00:00:00:00:00
R < 44:52:f0:20:00:02:00:00:00:00:00:00:00:18:44:52:2d:32:32:57:4c:20:00:00:00:00:00:00:00:00:00:71:00:45:00:65:00:0a
                                              ++ ++ ++ ++ ++ ++ ++ ++                            ++    ++    ++    ++
--
$ echo -n 'DR-22WL ' | hexdump -C
00000000  44 52 2d 32 32 57 4c 20                           |DR-22WL |
--
0x71 = 113 = Version 1.13
0x45 = 69 = Build 69
0x65 = 101 = Wifi 1.01
0x0a = 10 = Wifi 0.10
--

Rec/Play/Pause Button Pressed:
C > 44:52:10:41:00:08:00:00:00:00:00:00:00:00
                   ++
R < (status response from above)
--
Value changes between 07, 08, 09, 0b, 10
--