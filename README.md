Install
Update the User-Agent line near the top with your callsign/email (NWS requires this):
pythonHEADERS = {"User-Agent": "LinBPQ-WX/1.0 (W1AW; w1aw@arrl.org)"}
Then:

bash sudo cp wx_lookup.py /home/pi/linbpq/scripts/
sudo chmod 755 /home/pi/linbpq/scripts/wx_lookup.py
/etc/services — add:
wx  63013/tcp

/etc/inetd.conf — add:
wx  stream  tcp  nowait  pi  /home/pi/linbpq/scripts/wx_lookup.py  wx_lookup.py
bashsudo systemctl restart inetd
bpq32.cfg — add:
APP 5,WX,ATT 5  127.0.0.1 63013 TELNET LOOP,,WX,255 CONV

