import os
import subprocess
import urllib.request
from time import sleep
from urllib.error import ContentTooShortError

from PIL import Image

from airly import Airly

HOME = os.path.dirname(__file__)


def crop(image):
    img_down = image.crop((0, 524, image.size[0], 635))
    img_down.load()
    image.paste(img_down, (0, 400, image.size[0], 511))

    img_down = image.crop((0, 312, image.size[0], 511))
    img_down.load()
    image.paste(img_down, (0, 226, image.size[0], 425))

    image = image.crop((35, 0, image.size[0] - 40, 425))
    image.load()
    return image


def remove_logo(image):
    pixdata = image.load()
    for y in range(image.size[1]):
        for x in range(image.size[0]):
            if pixdata[x, y] == (255, 251, 240) or pixdata[x, y] == (244, 244, 244):
                pixdata[x, y] = (255, 255, 255)
            elif pixdata[x, y] == (216, 216, 216) or pixdata[x, y] == (215, 216, 215):
                pixdata[x, y] = (226, 226, 226)
    return image


def adjust_size(image):
    to_width = 600
    ratio = (to_width / float(image.size[0]))
    new_height = int((float(image.size[1]) * float(ratio)))
    image = image.resize((to_width, new_height), Image.LANCZOS)
    template = Image.open(os.path.join(HOME, 'template.png'))
    template.paste(image)
    return template


def paste_caqi(image):
    caqi = Image.open(os.path.join(HOME, 'caqi.png'))
    width, height = caqi.size
    caqi.load()
    image.paste(caqi, (0, 500, width, 500 + height))
    image.load()
    return image


if __name__ == '__main__':
    krakow = [466, 232]
    url = f'http://www.meteo.pl/um/metco/mgram_pict.php?ntype=0u&' \
          f'row={krakow[0]}&' \
          f'col={krakow[1]}&' \
          f'lang=pl'
    output = os.path.join(HOME, 'weather-script-output.png')
    smb_public_share = os.path.abspath('/home/dietpi/')
    airly = Airly()
    airly.fill_template()
    airly.plot_caqi_history()

    while True:
        try:
            urllib.request.urlretrieve(url, output)
            img = Image.open(output)
            img = img.convert('RGB')
        except [SyntaxError, OSError, ContentTooShortError]:
            print('\nDownload failed... retry in 15 seconds.\n')
            sleep(15)
            continue
        break

    img = crop(img)
    img = remove_logo(img)
    img = adjust_size(img)
    img = paste_caqi(img)
    img.save(output, bits=8)

    subprocess.run(['pngcrush', '-c', '0', output])
    subprocess.run(['mv', 'pngout.png', smb_public_share])
