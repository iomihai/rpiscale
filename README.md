# rpiscale
Raspberry Pi connected Wii Balance Board sends weight to Google Docs spreadsheet, shows it on an LCD and outputs text to speech

I had a balance board sitting around I built an Internet connected weighing scale based on https://github.com/skorokithakis/gr8w8upd8m8

I have used a Raspberry Pi 2 with Arch Linux with a LogiLink Bluetooth 4.0, Adapter USB 2.0 Micro and an 84x48 Nokia LCD Module Blue Backlight Adapter PCB with a SPI interface. 

This project should work on any Linux distribution and platform with adjustments but I have included detailed instructions for my setup.


### Installing:

Follow the steps on to install Arch Linux
https://archlinuxarm.org/platforms/armv7/broadcom/raspberry-pi-2#installation

After installing please change the default user passwords (root and alarm) to prevent your Pi becoming a botnet zombie.

#### Update the packages

```
pacman -Syy && pacman -Syu --noconfirm
```

#### Bluetooth installation
```
pacman -S --noconfirm bluez bluez-utils
systemctl enable --now bluetooth
```
For the bluetooth adapter to be powered on during startup create ```/etc/udev/rules.d/10-local.rules```

```
# Set bluetooth power up
ACTION=="add", KERNEL=="hci[0-9]*", RUN+="/usr/bin/hciconfig %k up"
```

Pair the board using ```bluetoothctl``` and enable the agent to connect the board when you press the balance board button

```
power on
agent on
default-agent
scan on
```

Press the sync button on the board (under the battery cover), replace xx:xx:xx:xx:xx:xx with the MAC address that appears on screen

```
pair xx:xx:xx:xx:xx:xx
trust xx:xx:xx:xx:xx:xx
exit
```

More info here
https://wiki.archlinux.org/index.php/bluetooth#Bluetoothctl

The latest update needs a config edit to be able for the bluetooth udev rule to work, if it does not powers on at start up, edit the systemd-udevd.service and add AF_BLUETOOTH at end of *RestrictAddressFamilies*

```
systemctl edit --full systemd-udevd.service
```
For me the line looks like
>RestrictAddressFamilies=AF_UNIX AF_NETLINK AF_INET AF_INET6 AF_BLUETOOTH


#### Python2

```
pacman -S --noconfirm python2-pip
pacman -S --noconfirm python2-numpy
pacman -S --noconfirm python2-gdata
pacman -S --noconfirm python2-systemd
pacman -S --noconfirm freetype2
pacman -S --noconfirm python2-pillow
```

##### Xwiimote

Install build dependencies
```
pacman -S --noconfirm base-devel git ncurses swig
```

Build and install xwiimote and xwiimote-bindings

```
git clone https://github.com/dvdhrm/xwiimote
cd xwiimote
./autogen.sh --prefix=/usr
make
make install
cd
rm xwiimote -rf

git clone https://github.com/dvdhrm/xwiimote-bindings
cd xwiimote-bindings
./autogen.sh --prefix=/usr
make
make install
cd
rm xwiimote-bindings -rf
```

##### LCD screen
Screen connections:

Screen pin|RST|CE|DC|DIN|CLK|VCC|LIGHT|GND
--- | --- | --- | --- | --- | --- | --- | --- | ---
Board pin|18|24|16|19|23|17|29|25
BCM pin|GPIO24|GPIO8|GPIO23|GPIO10|GPIO11|3v3|GPIO5|GND



Enable the SPI interface by adding to ```/boot/config.txt```
```
device_tree_param=spi=on
```
Install RPi.GPIO and Adafruit_GPIO
```
pip2 install RPi.GPIO
pip2 install Adafruit_GPIO
```
Build and install Adafruit_Nokia_LCD
```
git clone https://github.com/adafruit/Adafruit_Nokia_LCD.git
cd Adafruit_Nokia_LCD
python2 setup.py install
cd
rm Adafruit_Nokia_LCD -rf
```


#### Postgresql

##### Set the utf8 locale
```
sed -i 's/#en_US.UTF-8/en_US.UTF-8/' /etc/locale.gen
locale-gen
localectl set-locale LANG=en_US.UTF-8
```
##### Install Postgresql and create the database
```
pacman -S --noconfirm postgresql
pacman -S --noconfirm python2-psycopg2

chown -R postgres:postgres /var/lib/postgres/
runuser -l postgres -c "initdb --locale en_US.UTF-8 -E UTF8 -D '/var/lib/postgres/data'"
systemctl enable --now postgresql
runuser -l postgres -c "createdb rpiscale"
runuser -l postgres -c "createuser -S -D -R -e rpiscale"
```

#### Speech engine

```
pacman -S --noconfirm espeak
pacman -S --noconfirm alsa-utils
pip2 install pyttsx
```


#### Sound volume boost

I found the output volume of the RPi with a passive speaker too low.

Enable the audio interface by adding to ```/boot/config.txt```
```
dtparam=audio=on
```

Create ```/etc/asound.conf```
```
pcm.softvol {
        type softvol
        slave.pcm "cards.pcm.default"
        control {
                name "Software"
                card 0
        }
        max_dB 25.0
}
pcm.!default {
        type            plug
        slave.pcm       "softvol"
}
```
Set the volume and save it to make the changes permanent
```
alsactl init
aplay -l
amixer sset 'PCM' 100%
amixer sset 'Software' 100%
alsactl store
```
Check it with ```alsamixer```

### Project service

Checkout the project.
Go to the project folder

Create database tables
```
psql -U rpiscale < create_tables.sql
```

Create a blank Google spreadsheet https://docs.google.com/spreadsheets/u/0/

Get the spreadsheet_id from the spreadsheet link 
'''
https://docs.google.com/spreadsheets/d/*spreadsheet_id*/edit#gid=1023436007
'''

If you need them create more sheets.
Enter in each sheet in the first column first row cell ```date``` and the second column first row ```weight``` 

Get the sheets ids from
```
https://spreadsheets.google.com/feeds/worksheets/*spreadsheet_id*/private/full
```
inside the id tags in the form of
```
<id>https://spreadsheets.google.com/feeds/worksheets/*spreadsheet_id*/private/full/*sheet_id*</id>
```
The first sheet_id is always od6

Go to https://console.developers.google.com/apis/credentials , create a project if you need to and create a new OAuth 2.0 client ID for Other. Get the ClientID and Client secret.

Edit the config.py file and add your spreadsheet_id, gdata_client_id and gdata_secret.

Configure the sheets to match your spreadsheet file. You can have as many as you like as long as the weight ranges (the fourth parameter) do not overlap except for the last one set as a catch-all.

Edit disconnect.txt and replace xx:xx:xx:xx:xx:xx with the MAC address of your balance board

Run ```python2 rpiscale.py``` turn on the balance board, the LCD should light up. Stand still on the board until you hear over 5 beeps. Get off it and you should see a link on the terminal. 

Open that link in a browser to get the authorize token. Enter the authorize token into the prompt. This stores the token so you only have to do this once. 

Press ```Ctrl+c``` to end the script.

If the balance board does not connect, try the button again a few times, check the batteries, check the bluetooth adapter is up with ```hcitool dev``` and if it does not appear, bring it up with ```hciconfig hci0 up``` and redo the paiting/trust sequence.

Create ```/etc/systemd/system/rpiscale.service``` (adjust the script path to match your setup).
If you use the LCD screen you need to run it as root.

```
[Unit]
Description=Raspberry Pi Scale Service
After=postgresql.service bluetooth.service

[Service]
ExecStart=/usr/bin/python2.7 /root/rpiscale/rpiscale.py
PIDFile=/run/rpiscale.pid

[Install]
WantedBy=multi-user.target

```

Start at boot
```
systemctl enable --now rpiscale
```
### Attribution
I am using these Creative Commons fonts:
* http://www.dafont.com/pixel-unicode.font
* http://www.dafont.com/blocko.font

and this sound clip:
* https://freesound.org/people/timgormly/sounds/159760/
