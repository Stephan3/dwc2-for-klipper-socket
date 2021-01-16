# dwc2-for-klipper-socket

This is a rewrite of [dwc2-for-klipper](https://github.com/Stephan3/dwc2-for-klipper). As Klipper offers now a unixsocket API, its time to use it and run outside klippers main thread.

![screen](screenshots/screen.PNG?raw=true "screen")

### Things you shold know
- It works everywhere where klipper works, not only with duet boards
- Klipper is not RepRapFirmware
- This is a translator between [klipper](https://github.com/KevinOConnor/klipper) and [Duet Web Control](https://github.com/Duet3D/DuetWebControl)
- The DWC service can be restarted at any time without restarting klipper
- Sometimes buttons get a bad response - especially macros
  - Usually a timing issue
  - Make sure action gets performed
  - **Set AJAX retries to 0 for now:**
    - Settings > Machine-Specific > Number of maximum AJAX retries
- There is a configfile now 
- Klipper's printer.cfg is displayed as a virtual file (config.g) in system section
    - Restart after configuration edits works
- The macros you define in printer.cfg are displayed as virtual files wthin DWC's macros/klipper folder
- For pause and resume macros you can use:
    - Klipper gcode macros pause_print, resume_print, cancel_print (not case sensitive)
    - DWC macros pause.g, resume.g, cancel.g - this is in line with RRF
    - DWC macros are overriding Klipper's macros

### Installation ###

@th33xitus made a installer, see:
[Installer](https://github.com/th33xitus/kiauh)

##### Klipper needs to run with an additional arg ```-a /tmp/klippy_uds``` ####

This is my klipper systemd service located at ```/etc/systemd/system/klipper.service```
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
git clone https://github.com/Stephan3/dwc2-for-klipper-socket
pip3 install tornado

# get dwc:
mkdir -p ~/sdcard/web
cd ~/sdcard/web
wget https://github.com/Duet3D/DuetWebControl/releases/download/3.1.1/DuetWebControl-SD.zip
unzip *.zip && for f_ in $(find . | grep '.gz');do gunzip ${f_};done
rm DuetWebControl-SD.zip
```

dwc2-for-klipper-socket can run with systemd too. Here is the service I use for it, located at ```/etc/systemd/system/dwc.service```
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
