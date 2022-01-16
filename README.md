# RHi-Fi
Network streamer based on RPi4, Khadas Tone board and Mopidy. With custom box, buttons and LCD display. Can do everything Mopidy can do, and also act as a BT receiver and uPNP render.


Thanks to @nicokaiser for providing the [rpi-audio-receiver](https://github.com/nicokaiser/rpi-audio-receiver). I'm currently using the bluealsa version (commit b6eed00c51292ccface2f61d21526b0d74c93f5a), although gmrender resurrect wasn't working and had to be recompiled. Also, bluetooth audio lags behind and progressively falls noticeably out of sync. I'll try to switch to pulseaudio. 


Adjust the settings in i2c-lcd-drive.py according to your LCD hardware.


Execute both powerbutton.py and i2c-ldc-drive.py as systemd services. 
