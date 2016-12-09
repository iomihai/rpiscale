#!/usr/bin/env python2
# -*- coding: UTF-8 -*-

import errno
import os.path
import pickle
import logging
from systemd.journal import JournalHandler
import time
from datetime import datetime, timedelta
from operator import itemgetter
from select import poll, POLLIN
from subprocess import call, Popen

import Adafruit_GPIO.SPI as SPI
import Adafruit_Nokia_LCD as LCD
import RPi.GPIO as GPIO
import gdata.gauth
import gdata.spreadsheets.client
import numpy
import psycopg2
import pyttsx
import xwiimote
from PIL import Image, ImageDraw, ImageFont
from config import db_name, db_user, voice, spreadsheet_id, sheets, gdata_client_id, gdata_secret


log = logging.getLogger('balanceboard_scales')
log.addHandler(JournalHandler())
log.setLevel(logging.INFO)

conn = psycopg2.connect('dbname=%s user=%s' % (db_name, db_user))
conn.autocommit = True
cursor = conn.cursor()

pkg_folder = os.path.dirname(os.path.abspath(__file__))
timeout_last = datetime.now()

#-- screen setup
BACKLIGHT_PIN = 5
GPIO.setmode(GPIO.BCM)
GPIO.setup(BACKLIGHT_PIN, GPIO.OUT, initial=GPIO.HIGH)
DC = 23
RST = 24
SPI_PORT = 0
SPI_DEVICE = 0
disp = LCD.PCD8544(DC, RST, spi=SPI.SpiDev(SPI_PORT, SPI_DEVICE, max_speed_hz=4000000))
disp.begin(contrast=60)
disp.clear()
disp.display()
image = Image.new('1', (LCD.LCDWIDTH, LCD.LCDHEIGHT))
font = ImageFont.truetype(os.path.join(pkg_folder, 'fonts', 'Blocko.ttf'), 45)
small_font = ImageFont.truetype(os.path.join(pkg_folder, 'fonts', 'Pixel-UniCode.ttf'), 16)
draw = ImageDraw.Draw(image)

#-- speech setup
speech_engine = pyttsx.init()
speech_engine.setProperty('volume', 2)
speech_engine.setProperty('voice', voice)


def lcd_print(text_large, text_small=None):
    draw.rectangle((0, 0, 83, 47), outline=255, fill=255)
    draw.text((0, 10), text_large, font=font, fill=0)
    if text_small:
        draw.text((0, -5), text_small, font=small_font, fill=0)
    disp.image(image)
    disp.display()
    log.info(text_small + ' ' + text_large)


def speak(text):
    speech_engine.say(text)
    speech_engine.runAndWait()
    time.sleep(5)


def ding():
    global timeout_last
    timeout_last = datetime.now()
    Popen(['/usr/bin/aplay', os.path.join(pkg_folder, 'ding.wav')])


def write_sheet(sheet_weight, sheet_name):
    if not os.path.isfile(os.path.join(pkg_folder, 'gdata_token')):
        token = gdata.gauth.OAuth2Token(
            client_id=gdata_client_id,
            client_secret=gdata_secret,
            scope='https://spreadsheets.google.com/feeds/',
            user_agent='rpiscale.py')
        print(token.generate_authorize_url())
        verification_code = raw_input('What is the verification code? ').strip()
        token.get_access_token(verification_code)
        print(token.refresh_token)
        with open(os.path.join(pkg_folder, 'gdata_token'), 'w') as token_file:
            token_file.write(pickle.dumps(token))
    else:
        with open(os.path.join(pkg_folder, 'gdata_token'), 'r') as token_file:
            token = pickle.loads(token_file.read())

    spr_client = gdata.spreadsheets.client.SpreadsheetsClient()
    token.authorize(spr_client)

    for sheet in [s for s in sheets if s[0] == sheet_name]:
        entry = gdata.spreadsheets.data.ListEntry()
        entry.set_value('date', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        entry.set_value('weight', str(sheet_weight))
        lcd_print('{0:.2f}'.format(sheet_weight), 'saving in %s' % sheet[2])
        spr_client.add_list_entry(entry, spreadsheet_id, sheet[1])
        lcd_print('{0:.2f}'.format(sheet_weight), 'saved in %s' % sheet[2])
        return True

    return False


def connect():
    global timeout_last
    timeout_last = datetime.now()
    GPIO.output(BACKLIGHT_PIN, GPIO.LOW)


def disconnect():
    global timeout_last
    timeout_last = datetime.now()
    call('/usr/bin/bluetoothctl < %s' % os.path.join(pkg_folder, 'disconnect.txt'), shell=True)
    GPIO.output(BACKLIGHT_PIN, GPIO.HIGH)
    time.sleep(1)


log.info('=== ' + xwiimote.NAME_CORE + ' ===')

if __name__ == '__main__':
    while True:
        time.sleep(1)
        # list wiimotes and remember the first one
        try:
            mon = xwiimote.monitor(True, True)
            # print 'mon fd', mon.get_fd(False)
            ent = mon.poll()
            firstwiimote = ent
            while ent is not None:
                log.info('Found device: %s' % ent)
                ent = mon.poll()
        except SystemError as e:
            log.error('ooops, cannot create monitor %s' % e)

        # continue only if there is a wiimote
        if firstwiimote is None:
            # print 'No wiimote to read'
            continue

        # create a new iface
        try:
            dev = xwiimote.iface(firstwiimote)
        except IOError as e:
            log.error('ooops, %s' % e)
            exit(1)

        # display some information and open the iface
        try:
            fd = dev.get_fd()
            log.info('fd: %s' % fd)
            log.info('opened mask: %s' % dev.opened())
            dev.open(dev.available() | xwiimote.IFACE_WRITABLE)
            log.info('opened mask: %s' % dev.opened())
            log.info('devtype: %s' % dev.get_devtype())
            log.info('extension: %s' % dev.get_extension())

            connect()

        except SystemError as e:
            log.error('ooops %s' % e)
            exit(1)

        # read some values
        p = poll()
        p.register(fd, POLLIN)
        evt = xwiimote.event()
        n = 0
        measurement = None
        measurements = []
        weights = []
        stuck_weight = None
        weight_last_seen = None
        weight_count = None

        while n < 2:
            p.poll(1000)
            try:
                dev.dispatch(evt)
                if evt.type == xwiimote.EVENT_KEY:
                    code, state = evt.get_key()
                    log.info('Key: %s, State: %s' % (code, state))
                    n += 1
                elif evt.type == xwiimote.EVENT_GONE:
                    log.info('Gone')
                    n = 2
                elif evt.type == xwiimote.EVENT_WATCH:
                    log.info('Watch')
                    n = 2
                elif evt.type == xwiimote.EVENT_BALANCE_BOARD:
                    measurement = evt.get_abs(0)[0] + evt.get_abs(3)[0] + evt.get_abs(2)[0] + evt.get_abs(1)[0]
                else:
                    if evt.type != xwiimote.EVENT_ACCEL:
                        log.info('type: %s' % evt.type)

            except IOError as e:
                if e.errno != errno.EAGAIN:
                    log.error('Bad')

            if measurement:
                measurements.append(measurement)
                if len(measurements) == 20:
                    weight_mean = numpy.mean(measurements) / 100
                    weight_std = numpy.std(measurements) / 100
                    weight_std_percent = weight_std / weight_mean
                    measurements = []
                    if weight_std_percent < .002:
                        lcd_print('{0:.2f}'.format(weight_mean), '{0} {1:.5f}'.format(len(weights), weight_std_percent))
                        ding()
                        name = [s_name for s_name, _, _, s_lim in sheets if s_lim[0] < weight_mean < s_lim[1]][0]
                        cursor.execute('INSERT INTO weight (name, weight, stdev) VALUES (%s, %s, %s);',
                                       (name, weight_mean, weight_std))
                        weights.append((weight_mean, weight_std))

            if len(weights) > 5:
                if weight_last_seen and stuck_weight == weight_mean:
                    weight_count += 1
                else:
                    stuck_weight = weight_mean
                    weight_last_seen = datetime.now()
                    weight_count = 1
                log.info('%s %s %s %s' % (weight_mean, stuck_weight, datetime.now() - weight_last_seen, weight_count))

            if len(weights) > 5 and (weight_mean < 2 or datetime.now() - weight_last_seen > timedelta(seconds=3)):
                best_weight = min(weights, key=itemgetter(1))[0]  # get the weight having the least deviation
                name = [s_name for s_name, _, _, s_lim in sheets if s_lim[0] < best_weight < s_lim[1]][0]
                if write_sheet(best_weight, name):
                    speak('{} weighs {:.2f}'.format(name, best_weight))
                    disconnect()
                    n = 2

            if datetime.now() > timeout_last + timedelta(minutes=3):
                log.warn('timeout')
                disconnect()
                n = 2
