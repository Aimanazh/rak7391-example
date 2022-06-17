#!/usr/bin/env python3

import sys
import threading
import netifaces
import psutil
import re
import subprocess
import requests
import json

import board
import adafruit_ssd1306
from PIL import Image, ImageDraw, ImageFont

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

WIDTH = 128
HEIGHT = 64
BORDER = 5
DELAY = 5
AVAIL_WIDTH = 108
AVAIL_HIGH = 48
BUCKET_COUNT = 54
MIN_BUCKET = 18
MAX_BUCKET = 108
START_WIDTH = 8
START_HIGH = 12

# -----------------------------------------------------------------------------
# Pages
# -----------------------------------------------------------------------------


def intro(draw):

    # Draw a white background
    draw.rectangle((0, 0, oled.width - 1, oled.height - 1), outline=255, fill=255)

    # Draw a smaller inner rectangle
    draw.rectangle(
        (BORDER, BORDER, oled.width - BORDER - 1, oled.height - BORDER - 1),
        outline=0,
        fill=0,
    )

    # Write title
    text = "RAKPiOS"
    font = ImageFont.truetype("DejaVuSans-Bold", 20)
    (font_width, font_height) = font.getsize(text)
    draw.text((oled.width // 2  - font_width // 2, oled.height // 2 - 20), text, font=font, fill=255)

    # Version
    p = subprocess.run('cat /etc/os-release | grep VERSION_ID | sed \'s/.*"rakpios-\(.*\)"/\\1/\'', shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    text = p.stdout.decode()
    font = ImageFont.truetype("DejaVuSans-Bold", 10)
    (font_width, font_height) = font.getsize(text)
    draw.text((oled.width // 2 - font_width // 2, oled.height // 2 + 5), text, font=font, fill=255)

    return True

def network(draw):
    
    # Create blank image for drawing
    font = ImageFont.load_default()
    (font_width, font_height) = font.getsize("H")
    y = 0
    
    draw.rectangle((0, 0, oled.width - 1, font_height - 1), outline=255, fill=255)
    draw.text((0, y), "NETWORK", font=font, fill=0)
    y += font_height

    # Get IP
    ifaces = netifaces.interfaces()
    pattern = "^bond.*|^[ewr].*|^br.*|^lt.*|^umts.*|^lan.*"

    # Get bridge interfaces created by docker 
    p = subprocess.run('docker network ls -f driver=bridge --format "br-{{.ID}}"', shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    br_docker_ifaces = p.stdout.decode()
    
    for iface in ifaces:
        # Match only interface names starting with e (Ethernet), br (bridge), w (wireless), r (some Ralink drivers use>
        # Get rid off of the br interface created by docker
        if re.match(pattern, iface) and iface not in br_docker_ifaces:
            ifaddresses = netifaces.ifaddresses(iface)
            ipv4_addresses = ifaddresses.get(netifaces.AF_INET)
            if ipv4_addresses:
                for address in ipv4_addresses:
                    addr = address['addr']
                    draw.text((0, y), ("%s: %s" % (iface[:6], addr)), font=font, fill=255)
                    y += font_height

    return True

def stats(draw):
    
    # Create blank image for drawing
    font = ImageFont.load_default()
    (font_width, font_height) = font.getsize("H")
    y = 0
    
    draw.rectangle((0, 0, oled.width - 1, font_height - 1), outline=255, fill=255)
    draw.text((0, y), "STATS", font=font, fill=0)
    y += font_height

    # Get cpu percent
    cpu = psutil.cpu_percent(None)
    draw.text((0, y), ("CPU: %.1f%%" % cpu), font=font, fill=255)
    y += font_height
 
    # Get free memory percent
    memory = 100 - psutil.virtual_memory().percent
    draw.text((0, y), ("Free memory: %.1f%%" % memory), font=font, fill=255)
    y += font_height

    # Get temperature
    p = subprocess.run('vcgencmd measure_temp 2> /dev/null | sed \'s/temp=//\'', shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    draw.text((0, y), ("Temperature: %s" % p.stdout.decode()), font=font, fill=255)
    y += font_height

    # Get uptime
    p = subprocess.run('uptime -p | sed \'s/up //\' | sed \'s/ hours*/h/\' | sed \'s/ minutes*/m/\' | sed \'s/,//\'', shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    draw.text((0, y), ("Uptime: %s" % p.stdout.decode()), font=font, fill=255)
    y += font_height

    return True

def docker(draw):
    
    # Get the list of docker services
    p = subprocess.run('docker ps -a --format \'{{.Names}}\t{{.Status}}\' | sort -r -k2 -k1 | awk \'{ print $1, $2 }\' | sed \'s/Exited/Down/\'', shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    services = p.stdout.decode().split('\n')[:-1]
    limit = len(services)
    if limit > 5:
        limit = 4
    
    # If no docker services do not display this page
    if limit == 0:
        return False

    # Create blank image for drawing
    font = ImageFont.load_default()
    (font_width, font_height) = font.getsize("H")
    y = 0

    # Title
    draw.rectangle((0, 0, oled.width - 1, font_height - 1), outline=255, fill=255)
    draw.text((0, y), "DOCKER", font=font, fill=0)
    y += font_height

    # Show services and status
    for service in services[:limit]:
        (name, status) = service.split(' ')
        draw.text((0, y), name.lower().ljust(17)[:17] + status.upper().rjust(4), font=font, fill=255)
        y += font_height
    if len(services) > limit:
        draw.text((0, y), "... and %d more" % (len(services)-limit), font=font, fill=255)
        y += font_height

    return True

def lorawan(draw):

    font = ImageFont.load_default()
    (font_width, font_height) = font.getsize("H")

    # draw y-axis, the packet count of each bucket.
    draw.line((3, 0, 3, 60), width=1, fill=128)
    draw.line((3, 0, 0, 3), width=1, fill=128)
    draw.line((3, 0, 6, 3), width=1, fill=128)

    # draw x-axis, the time.
    draw.line((3, 60, 127, 60), width=1, fill=128)
    draw.line((124, 63, 127, 60), width=1, fill=128)
    draw.line((124, 57, 127, 60), width=1, fill=128)
    draw.text((121, 45), "t", font=font, fill=255)

    # draw y-axis metric.
    draw.line((3, 48, 5, 48), width=1, fill=128)
    draw.line((3, 36, 5, 36), width=1, fill=128)
    draw.line((3, 24, 5, 24), width=1, fill=128)
    draw.line((3, 12, 5, 12), width=1, fill=128)

    # calculate the width of each bucket and real bucket count displayed.

    if AVAIL_WIDTH % BUCKET_COUNT:
        bucket_width = AVAIL_WIDTH / BUCKET_COUNT + 1
        bucket_count = AVAIL_WIDTH / bucket_width
    else:
        bucket_width = AVAIL_WIDTH / BUCKET_COUNT
        bucket_count = BUCKET_COUNT

    # require bucket data from log2api
    url = "http://127.0.0.1:8888/api/metrics"
    try:
        res = requests.get(url)
    except:
        draw.rectangle((0, 0, oled.width - 1, oled.height - 1),
                   outline=255, fill=0)
        return False

    bucket_data = json.loads(res.text)
    buckets = bucket_data['buckets']
    totals = bucket_data['totals']

    # Don't display if no packet
    rx_max = totals['rx_max']
    if rx_max == 0:
        return True

    # calculate the pixel of every packet
    unit = float(AVAIL_HIGH / rx_max)

    # draw every bucket 
    for i in range(bucket_count):
        tmp = buckets.get(str(BUCKET_COUNT - bucket_count + i), {'rx': 0, 'tx': 0})
        rx = tmp['rx']

        draw.rectangle((START_WIDTH + i * bucket_width, 60, START_WIDTH + (i + 1) * bucket_width - 1,

                        60 - int(rx * unit)), outline=1, fill=1)
    # draw top line
    top = "SIZE:%d MAX:%d"%(bucket_count, rx_max)
    draw.text((10, 0), top, font=font, fill=255)
    
    return True

# -----------------------------------------------------------------------------
# State machine
# -----------------------------------------------------------------------------

def show_page(page):

    # Prepare canvas
    image = Image.new("1", (oled.width, oled.height))
    draw = ImageDraw.Draw(image)

    response = False
    while not response:
        
        # Show page (returns false if the page should not be displayed)
        response = pages[page](draw)
        
        # Update next page
        # We are not showing page 0 (intro) again
        page = page + 1
        if page >= len(pages):
            page = 1


    # Update screen
    oled.fill(0)
    oled.image(image)
    oled.show()
    
    # Return pointer to next page
    return page

# -----------------------------------------------------------------------------
# Main loop
# -----------------------------------------------------------------------------

class RepeatTimer(threading.Timer):
    page = 1
    def run(self):
        while not self.finished.wait(self.interval):
            self.page = self.function(self.page, *self.args, **self.kwargs)

try:
    i2c = board.I2C()
    oled = adafruit_ssd1306.SSD1306_I2C(WIDTH, HEIGHT, i2c)
except Exception:
    print("OLED screen not found")
    sys.exit()

pages = [intro, network, docker, stats, lorawan]
show_page(0)
timer = RepeatTimer(DELAY, show_page)
timer.start()
