# meteo-to-kindle
Fetches image from meteo and manipulates it to be properly displayed on e-ink

This script feches image with weather forecast from meteo.pl.
## ONLY FOR POLAND
and outputs it in Kindle-friendly format.

The kindle launches download of the image and displays it.
If battery leves drops down below 5% displays warning to charge the device.

The jobs are triggered by crontab. I'm using Raspberry Pi Zero W as a host and Lacie NAS as a storage.

![alt text](https://github.com/cielke/meteo-to-kindle/raw/master/20180508_162118.jpg)
