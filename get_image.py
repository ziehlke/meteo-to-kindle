import subprocess
import urllib.request
from time import sleep
from urllib.error import ContentTooShortError

from PIL import Image


def crop(image):
    img_down = image.crop((0, 524, 585, 635))
    img_down.load()
    image.paste(img_down, (0, 400, 585, 511))
    image = image.crop((35, 0, 540, 511))
    image.load()
    return image


def removeLogo(image):
    pixdata = image.load()
    for y in range(image.size[1]):
        for x in range(image.size[0]):
            if pixdata[x, y] == (255, 251, 240) or pixdata[x, y] == (244, 244, 244):
                pixdata[x, y] = (255, 255, 255)
            elif pixdata[x, y] == (216, 216, 216) or pixdata[x, y] == (215, 216, 215):
                pixdata[x, y] = (226, 226, 226)
    return image


def adjustSize(image):
    to_width = 600
    ratio = (to_width / float(image.size[0]))
    new_height = int((float(image.size[1]) * float(ratio)))
    image = image.resize((to_width, new_height), Image.ANTIALIAS)
    template = Image.open("/mnt/OpenShare/weather/template.png")
    template.paste(image)
    return template


if __name__ == '__main__':
    #  Gdansk = [346, 210]
    Krakow = [466, 232]
    url = f"http://www.meteo.pl/um/metco/mgram_pict.php?ntype=0u&" \
          f"row={Krakow[0]}&" \
          f"col={Krakow[1]}&" \
          f"lang=pl"
    output = "/mnt/OpenShare/weather/weather-script-output.png"

    while True:
        try:
            urllib.request.urlretrieve(url, output)
            img = Image.open(output)
            img = img.convert("RGB")
        except [SyntaxError, OSError, ContentTooShortError]:
            print("\nDownload failed... retry in 15 seconds.\n")
            sleep(15)
            continue
        break

    img = crop(img)
    img = removeLogo(img)
    img = adjustSize(img)
    img.save(output, bits=8)

    subprocess.run(['pngcrush', '-c', '0', output])
    subprocess.run(['mv', 'pngout.png', output])
