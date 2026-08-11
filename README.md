# meteo-to-kindle

Fetches a weather forecast image from meteo.pl (**Poland only**), overlays
current air quality data from Airly, and converts it into a Kindle-friendly format.

The Kindle downloads the image and displays it on its e-ink screen.
If the battery level drops below 30%, it also displays a warning to charge
the device; below 10% it shows the warning and puts itself to sleep.

The jobs are triggered by crontab. I'm using a Raspberry Pi Zero W as the host
and a LaCie NAS for storage.

![Kindle displaying the weather forecast](https://github.com/cielke/meteo-to-kindle/raw/master/20180508_162118.jpg)
