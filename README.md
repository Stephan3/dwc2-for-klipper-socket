# dwc2-for-klipper-socket
dwc2-for-klipper using klippers unixsocket. runs offthread and all tasks are nonblocking now. This should do a ton better.

new version readme tbd
run klipper like:
```/usr/bin/python2 /root/klipper/klippy/klippy.py /root/printer.cfg -l /tmp/klippy.log -a /tmp/klippy_uds```


run dwc like:
```/usr/bin/python3 /root/dwc2-for-klipper-socket/web_dwc2.py```

one can use systemd to run that. Fo now i am on 4 rigs live and cover all things that happen there.
