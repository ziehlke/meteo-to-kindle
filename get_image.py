import urllib.request
from time import sleep
from PIL import Image


def download(url):
    urllib.request.urlretrieve(
        url, "/mnt/OpenShare/weather/weather-script-output.png")
    img = Image.open("weather-script-output.png")
    return None


def crop(img):
    img_down = img.crop((0, 524, 585, 635))
    img_down.load()
    img.paste(img_down, (0, 400, 585, 511))
    img = img.crop((35, 0, 585, 511))
    img.load()
    return img


def color(img):
    pixdata = img.load()
    for y in range(img.size[1]):
        for x in range(img.size[0]):
            if pixdata[x, y] == (255, 251, 240):
                pixdata[x, y] = (255, 255, 255)
    return img


if __name__ == '__main__':
    url = "http://www.meteo.pl/um/metco/mgram_pict.php?ntype=0u&row=346&col=210&lang=pl"
    download(url)
    img = Image.open("weather-script-output.png")
    img = img.convert("RGB")
    img = crop(img)
    img = color(img)

    # 505 x 511
    img.save("weather-script-output.png")
