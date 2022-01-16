#!/usr/bin/env python

import RPi.GPIO as gpio
from time import sleep
from subprocess import call

from datetime import datetime


## pin che ascolta per il segnale di spegnimento dal power module
pinButton = 21 #BCM


## MAIN ROUTINE
def arresto_cb(self):
    #print("segnale di spegnimento ricevuto!")
    sleep(2)
    if (gpio.input(pinButton)):
        #se il pulsante è stato premuto per 2 secondi, allora:
        #print("spegnimento!")
        call(['shutdown', '-h', 'now'], shell=False)



## HW SETUP
try:
    gpio.setmode(gpio.BCM)

    gpio.setup(pinButton, gpio.IN, pull_up_down=gpio.PUD_DOWN) # se il cavo non è collegato, e quindi il sengale è floating, pull$
    gpio.add_event_detect(pinButton, gpio.FALLING, callback=arresto_cb, bouncetime=200) # usiamo un interrupt. Bouncetime serve a ignorare il jitter
    
    while True:
        # keep alive
        sleep(60)

finally:
    gpio.cleanup()
