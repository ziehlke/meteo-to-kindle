#!~/virtualenv/Pillow/bin python
import urllib.request
from time import sleep
from PIL import Image


def download(url):
    urllib.request.urlretrieve(
        url, "/mnt/OpenShare/weather/weather-script-output.png")
    return None


def crop(img):
    img_down = img.crop((0, 524, 585, 635))
    img_down.load()
    img.paste(img_down, (0, 400, 585, 511))
    img = img.crop((35, 0, 540, 511))
    img.load()
    return img


def color(img):
    pixdata = img.load()
    for y in range(img.size[1]):
        for x in range(img.size[0]):
            if pixdata[x, y] == (255, 251, 240) or pixdata[x, y] == (244, 244, 244):
                pixdata[x, y] = (255, 255, 255)
            elif pixdata[x, y] == (216, 216, 216) or pixdata[x, y] == (215, 216, 215):
                pixdata[x, y] = (226, 226, 226)
    return img


def adjustSize(img):
    toWidth = 600
    ratio = (toWidth / float(img.size[0]))
    newHeight = int((float(img.size[1]) * float(ratio)))
    img = img.resize((toWidth, newHeight), Image.ANTIALIAS)
    return img


if __name__ == '__main__':
    # 346, 210 - for Gdansk
    url = "http://www.meteo.pl/um/metco/mgram_pict.php?ntype=0u&row={}&col={}&lang=pl".format(
        346, 210)
    download(url)
    while True:
        try:
            img = Image.open("weather-script-output.png")
            img = img.convert("RGB")
        except (SyntaxError, OSError):
            print("\nDownload failed... retry in 15 seconds.\n")
            sleep(15)
            download(url)
            img = Image.open("weather-script-output.png")
            img = img.convert("RGB")
            continue
        break

    img = crop(img)
    img = color(img)
    img = img.convert('L')
    img = adjustSize(img)
    img.save("weather-script-output.png")
