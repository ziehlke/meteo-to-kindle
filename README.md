# meteo-to-kindle

Fetches a weather forecast image from meteo.pl (**Poland only**), overlays
current air quality data from Airly, and converts it into a Kindle-friendly format.

The Kindle downloads the image and displays it on its e-ink screen.
If the battery level drops below 30%, it also displays a warning to charge
the device; below 10% it shows the warning and puts itself to sleep.

The jobs are triggered by crontab. I'm using a Raspberry Pi Zero W as the host
and a LaCie NAS for storage.

## Install and run

This is an installable Python application. On the Raspberry Pi, install Python
3.12+, `uv`, and `pngcrush` (optional; used to compress the published image),
then run:

```sh
uv sync
cp .env.example .env
# Set AIRLY_KEY in .env, then:
uv run meteo-to-kindle
```

The command can also be run as `uv run python -m meteo_to_kindle`. Set
`METEO_OUTPUT_DIR` to choose where generated images are written, and
`METEO_SHARE_PATH` to choose the mounted directory where the Kindle fetches the
image. Both default to the current directory and `/home/dietpi`, respectively.
The bundled template and fonts are read from the installed package.

## Kindle FTP credentials

The Kindle-side `client-kindle/display-weather.sh` reads `FTP_USER` and
`FTP_PASSWORD` from `/var/local/meteo-to-kindle/credentials`, a shell config
file. Keep this off `/mnt/us` (the USB-exported storage), where file permissions
may not protect it. On the Kindle, copy `client-kindle/credentials.example`
into that path, put the real credentials in it, and restrict it:

```sh
mkdir -p /var/local/meteo-to-kindle
cp /mnt/us/weather/credentials.example /var/local/meteo-to-kindle/credentials
chmod 700 /var/local/meteo-to-kindle
chmod 600 /var/local/meteo-to-kindle/credentials
```

The script sources this file itself, so cron does not need to inherit an
interactive shell's environment. Use a dedicated, read-only FTP account with a
URL-safe password, and rotate any credentials previously embedded in the
script. FTP does not encrypt credentials in transit; keep it limited to a
trusted local network.

![Kindle displaying the weather forecast](https://github.com/cielke/meteo-to-kindle/raw/master/20180508_162118.jpg)
