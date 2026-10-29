# meteo-to-kindle

Fetches hourly forecast data from the Meteo ICM API (the JSON backend behind
[app.meteo.pl](https://app.meteo.pl), **Poland only**), renders its own
grayscale meteogram, overlays current air quality data from Airly, and formats
everything for a Kindle e-ink display.

The Kindle downloads the image and displays it on its e-ink screen.
If the battery level drops below 30%, it also displays a warning to charge
the device; below 10% it shows the warning and puts itself to sleep.

The jobs are triggered by crontab. I'm using a Raspberry Pi Zero W as the host
and a LaCie NAS for storage.

## Install and run

This is an installable Python application. On the Raspberry Pi, install Python
3.14+, `uv`, and `pngcrush` (required to publish to `METEO_SHARE_PATH`; without
it, the image is only written to `METEO_OUTPUT_DIR`), then run:

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

### Weather models

The forecast point is the same one used for Airly. `METEO_MODEL` selects the
forecast model (default `um4_60`):

| Model | Horizon |
| --- | --- |
| `um4_60` | UM 4 km, 60 h hourly |
| `um4_120` | UM 4 km, 120 h hourly |
| `gfs` | GFS, 240 h hourly |

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
interactive shell's environment, and it re-checks the modes above first:
it refuses to run if the file or its directory is more open than
documented, or owned by someone else. Use a dedicated, read-only FTP
account; credentials may contain spaces or quotes, since the script
encodes them for the netrc format. Before each download it derives a
`chmod 600` netrc file in that same directory and passes it to wget
(`--netrc-file`), so the FTP password never appears on wget's command
line, where another local process could see it in `ps`. FTP does not
encrypt credentials in transit; keep it limited to the networks you
actually trust.

![Kindle displaying the weather forecast](https://github.com/cielke/meteo-to-kindle/raw/master/20180508_162118.jpg)
