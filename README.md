# dwc2-for-klipper-socket

This is a rewrite of [dwc2-for-klipper](https://github.com/Stephan3/dwc2-for-klipper). As Klipper offers now a unixsocket API,
its time to use it and run outside klippers main thread.

### Things you shold know
- Klipper is not RepRapFirmware
- you can restart dwc service at any time without restarting klipper
- Sometimes buttons get a bad response
  - usually a timing issue
  - make sure action gets performed
  - **set AJAX retries  for now to 0**
    - Settings > Machine-Specific > Number of maximum AJAX retries
- there is a configfile now 
- Klipper's printer.cfg is displayed as a virtual file (config.g) in system section
    - restart after configuration edits works
- The macros you define in printer.cfg are displayed as virtual files wthin DWC's macros/klipper folder
- For pause and resume macros you can use:
    - Klipper gcode macros pause_print, resume_print, cancel_print (not case sensitive)
    - DWC macros pause.g, resume.g, cancel.g - this is in line with RRF
    - DWC macros are overriding Klipper's macros

### Installation ###

##### Klipper needs to run with a aditional arg -a /tmp/klippy_uds ####

This s my klipper systemd service located at ```/etc/systemd/system/klipper.service```
```
[Unit]
Description=klipper pinter service
After=network.target

[Service]
User=pi
Group=pi
ExecStart=/usr/bin/python2 /home/pi/klipper/klippy/klippy.py /home/pi/printer.cfg -l /tmp/klippy.log -a /tmp/klippy_uds
WorkingDirectory=/root/klipper

[Install]
WantedBy=multi-user.target
```

---- todo add /etc/default here ----

Make sure klipper is up and running with unixsocket enabled before next steps.

```
# clone this repo:
cd ~
git clone git@github.com:Stephan3/dwc2-for-klipper-socket.git
pip3 install tornado

# get dwc:
mkdir -p ~/sdcard/web
cd ~/sdcard/web
wget https://github.com/Duet3D/DuetWebControl/releases/download/3.1.1/DuetWebControl-SD.zip
unzip *.zip && for f_ in $(find . | grep '.gz');do gunzip ${f_};done
```

dwc2-for-klipper-socket can rund with systemd too. here is the service i use for it, located at ```/etc/systemd/system/dwc.service```
```
[Unit]
Description=dwc_webif
After=klipper.service

[Service]
ExecStart=/usr/bin/python3 /home/pi/dwc2-for-klipper-socket/web_dwc2.py
WorkingDirectory=/home/pi/dwc2-for-klipper-socket

[Install]
WantedBy=multi-user.target
```
Please make sure that all paths matching your setup. 

You might want to reload your services with ```systemctl daemon-reload```
The webinterface can be launched by ```systemctl start dwc``` and enabled at startup ```systemctl enable dwc```
