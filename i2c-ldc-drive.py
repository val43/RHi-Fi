### Valentino Mariotto 2020 ###

import re       # regex lib
import logging
import sys
import signal
import socket
from RPLCD      import i2c
from mpd        import MPDClient
from time       import sleep
from threading  import Thread#, Condition, Event


## speed settings
scrolling_delay = 0.6 # seconds
info_refresh_delay = 1 # seconds
i2c_refresh_delay = 0.3 # seconds

## MPD settings
mpdHost = "localhost"
mpdPort = 6600

## logging setup
errorbuffer = ""
logging.basicConfig(filename='/home/pi/logs/mopidyLCDdrive.py.log', \
                    filemode='a', \
                    format='%(asctime)s %(levelname)s: %(message)s', \
                    level=logging.WARNING)


## Initialise the LCD
displayCols = 16    # 16 or 20
displayRows = 2     # 1, 2 or 4
stateIcoPosition = (0,0) #primo carattere, prima riga, riservato per simbolo di stato
charmap = 'A00'             # A00 or A02 or ST0B
auto_linebreaks = True      # False non funziona (risolto qui https://github.com/dbrgn/RPLCD/pull/109), true causa sovrapposizioni
dotsize = 8                 # 8 or 10 pixel char height
lcdmode = 'i2c'             #
i2c_expander = 'PCF8574'    # “PCF8574”, “MCP23008”, “MCP23017”.
#expander_params={‘gpio_bank’:‘A’}  # only for MCP23017 - A or B
address = 0x27              # Find using: i2cdetect -y 1
port = 1                    # 0 on an older Raspberry Pi

play = (	0b00000,
            0b10000,
            0b11000,
            0b11100,
            0b11110,
            0b11100,
            0b11000,
            0b10000)
pause = (   0b00000,
            0b00000,
            0b11011,
            0b11011,
            0b11011,
            0b11011,
            0b11011,
            0b00000)
stop = (	0b00000,
            0b00000,
            0b11111,
            0b11111,
            0b11111,
            0b11111,
            0b11111,
            0b00000)



class GracefulKiller:
  kill_now = False
  def __init__(self):
    signal.signal(signal.SIGINT, self.exit_gracefully)
    signal.signal(signal.SIGTERM, self.exit_gracefully)

  def exit_gracefully(self,signum, frame):
    self.kill_now = True
    


class Display:
    def __init__(self):
        self.rows = displayRows
        self.cols = displayCols
        self.stateIcoP = stateIcoPosition
        self.buffered = ""
        self.linebuffers = [""] * self.rows
        self.composed = [""] * self.rows
        self.scrollTo = [0] * self.rows
        self.schema =   [{ # riga 0
                            "Stop": ["sys.Freq", "sys.BitStr", "mpd.Volume"],
                            "Play": ["mpd.State", "song.Title"],
                            "Pause":["mpd.State", "sys.Freq", "sys.BitStr", "mpd.Volume"]
                        },{ # riga 1
                            "Stop": ["sys.IPv4","sys.Temp"],
                            "Play": ["song.Artist"],
                            "Pause":["song.Artist", "song.Title"]
                        }]        
        self.data =   { "sys.Freq":     {"v": getFreq(),  "updt": True, "blck": False,  "cmd": "getFreq()"     },
                        "sys.BitStr":   {"v": getBitStr(),"updt": True, "blck": False,  "cmd": "getBitStr()"   },
                        "sys.IPv4":     {"v": getIPv4(),  "updt": False,"blck": False,  "cmd": "getIPv4()"     },
                        "sys.Temp":     {"v": "",         "updt": True, "blck": False,  "cmd": "getTemp()"     },
                        "mpd.Volume":   {"v": "",         "updt": True, "blck": False,  "cmd": "getVolume(mpdStatus)"              },
                        "mpd.State":    {"v": "",         "updt": True, "blck": True,   "cmd": "stateIcons[getState(mpdStatus)]"   }, 
                        "song.Title":   {"v": "",         "updt": True, "blck": True,   "cmd": "getTitle(mpdSong)"                 },
                        "song.Artist":  {"v": "",         "updt": True, "blck": True,   "cmd": "getArtist(mpdSong)"                } }
                        
    # def clearRow(self, row):
        # self.events[0].clear() # impedisco scrolling
        # lcd.cursor_pos = (row, self.cursX)
        # lcd.write_string(' ' * self.cols) # -1 se auto_linebreaks=False
        # sleep(i2c_refresh_delay)
        
        
    def compose(self, mpdc):
        global errorbuffer
        comp = [""] * self.rows
        try:
            errorbuffer = ""
            mpdStatus = mpdc.status()
            mpdSong =   mpdc.currentsong()
            mpdState =  "Stop" if not mpdSong else getState(mpdStatus) #mpd non riporta lo stato STOP correttamente
            #print(mpdState)
            
            for row in range(self.rows):
                composition = ""
                
                for datum in self.schema[row][mpdState]:
                    item = self.data[datum]
                    
                    if item["updt"]:
                        if datum.split()[0] == "song" and not mpdSong:
                            item["v"] = ""
                        else:
                            itemNewVal = eval(item["cmd"])
                            if itemNewVal != item["v"] and item["blck"]:
                                self.scrollTo[row] = 0 # per far ripartire scrolling dall'inizio
                            item["v"] = itemNewVal
                            
                    composition += item["v"]+" "
                
                self.composed[row] = composition[0:-1].ljust(self.cols, ' ') #aggiungo spazi se necessario
                #print(self.composed)
        except Exception:
            logging.critical("Impossibile ottenere info da MPD")
            errorbuffer += " MPD error "
        
                
    def refresh(self):
        # while True:
        try:
            buffer = "\r\n".join(self.linebuffers) # mando una stringa unica al driver del display
            if self.buffered != buffer:
                print(buffer)
                self.buffered = buffer
                lcd.cursor_pos = (0,0)
                lcd.write_string(buffer)
        except Exception as err:
            logging.critical(err)
            raise SystemExit
        #sleep(i2c_refresh_delay)


    def scroll(self):
        global errorbuffer
        padding = '   '
        
        while True:
            try:
                print(self.scrollTo)
                for n, row in enumerate(self.composed):
                    if n == self.stateIcoP[0] and row[0:1] in stateIcons.values():
                        begin = 1 # tengo ferma icona di stato
                    elif n != self.stateIcoP[0]:
                        begin = 0
                        if errorbuffer != "": # mostro errori su seconda riga
                            #print(errorbuffer)
                            row = errorbuffer.ljust(self.cols, " ")
                    
                    if len(row) > self.cols:
                        i = self.scrollTo[n] + begin
                        padrow = row[begin:] + padding + row[begin:]
                        self.linebuffers[n] = row[0:begin] + padrow[i:i+self.cols-begin] # scrolling 1 char at a time, except for state icon (row[0:begin])
                        self.linebuffers[n] = self.linebuffers[n].ljust(self.cols)[:self.cols] # truncating at the maximum allowed length
                        if self.scrollTo[n] >= len(row+padding)-1:
                            self.scrollTo[n] = 0 #azzero quando l'inizio della selezione coincide con l'inizio del testo
                        else:
                            self.scrollTo[n] += 1 
                        
                    else:
                        self.linebuffers[n] = row#[:self.cols]
                    
                self.refresh()
                
            except Exception as err:
                logging.error(err)
                errorbuffer += " "+type(err).__name__+" "
                
            finally:
                sleep(scrolling_delay)
            


# ottengo nuove informazioni. Eliminare la classe e usare funzioni singole?? così si può usare eval() e semplificare compose() @@
def getIPv4():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # doesn't even have to be reachable
        s.connect(('10.255.255.255', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = ""
        pass
    finally:
        s.close()
        return ip
        
        
def getTemp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as t:
            return "{0:.1f}°C".format(int(t.read())/1000)
    except:
        logging.warning("couldn't get temperature")
        return False
        
        
def getFreq():
    try:
        with open('/proc/asound/card0/pcm0p/sub0/hw_params', 'r') as card0:
            hwinfos = card0.readlines()
        
        if len(hwinfos)<=1:
            # scheda audio spenta!
            return "--KHz"
        else:
            freq = int((hwinfos[4])[6:12])/1000
            return "{0:.0f}kHz".format(freq) #{0:.1f}kHz

    except IOError:
        # scheda audio non rilevata
        logging.warning("no audio output")
        return False


def getBitStr():
    try:
        with open('/proc/asound/card0/pcm0p/sub0/hw_params', 'r') as card0:
            hwinfos = card0.readlines()
        
        if len(hwinfos)<=1:
            # scheda audio spenta!
            return "--b"
        
        else:
            # scheda in uso                
            bits = re.compile("(16|24|32)")
            matchR = bits.search(hwinfos[1])
            if matchR:
                return matchR.group(1) + "b"
            else:
                return "--b"
            # print(dati['bitStr'])
            # logging.debug(dati['bitStr'])
            
    except IOError:
        # scheda audio non rilevata
        logging.warning("no audio output")
        return False


def getState(mpd):
    return mpd['state'].capitalize()
        
def getVolume(mpd):
    return mpd['volume'] + "%v"
       
def getArtist(song):
    return song['artist']
        
def getAlbum(song):
    return song['album'] 
        
def getTitle(song):
    return song['title']
    



## MAIN
if __name__ == '__main__':

    killer = GracefulKiller()
    
    # option to stop the service
    if len(sys.argv) > 1 and sys.argv[1] == "stop":
        raise SystemExit
    
    
    ## LCD
    try:
        lcd = i2c.CharLCD(i2c_expander=i2c_expander, address=address, port=port, 
                          charmap=charmap, auto_linebreaks=auto_linebreaks, 
                          cols=displayCols, rows=displayRows, dotsize=dotsize,
                          backlight_enabled=True)
        
        lcd.create_char(0, stop)
        lcd.create_char(1, play)
        lcd.create_char(2, pause)
        stateIcons = {  "Play": '\x01',
                        "Pause":'\x02',
                        "Stop": '\x00' }
        lcd.cursor_mode = 'hide'
        logging.info("Display OK")
        
    except IOError:
        logging.critical("Nessun display LCD")
        #print("ERRORE: nessun display LCD")
        raise SystemExit
    
    
    
    ## MPD
    try:
        ## Connect to mpd client
        mpdc = MPDClient()
        # diamo tempo a mopidy di partire, ma se ci mette troppo generiamo un errore
        #mpdc.timeout = 60 #seconds
        mpdc.connect(mpdHost, mpdPort)
        
    except Exception as err:
        # if str(err) == 'Already connected':
            # normale, siamo già collegati
            # pass
        # else:
        # raccogliamo tutti gli altri errori
        #print(err)
        logging.error(err)
        errorbuffer += " "+type(err).__name__+" "
        mpdc = None
    
    
    x216 = Display()
    
    ## threading
    scrolling = Thread(target=x216.scroll, daemon=True) #daemon thread is killed upon exit
    scrolling.start()

   
    ## MAIN LOOP
    while not killer.kill_now:
        try:
            x216.compose(mpdc)
            sleep(info_refresh_delay)
        
        except KeyboardInterrupt:
            lcd.close(clear=True)
            mpdc.close()
            mpdc.disconnect()
            logging.info("Terminato dall'utente, uscita forzata")
            sys.exit(130)
        
    # è intervenuto un SIGTERM ma l'abbiamo intercettato. Graceful exit:
    lcd.close(clear=True)
    logging.info("Arresto del sistema, uscita forzata")


