#!/bin/sh


NAME=display-weather
SCRIPTDIR="/mnt/us/weather"
LOG="$SCRIPTDIR/$NAME.log"

LIMG="$SCRIPTDIR/weather-script-output.png"
LIMGERR="$SCRIPTDIR/weather-error.png"
LIMGBATT="$SCRIPTDIR/weather-battery.png"

RIMG="192.168.1.125/OpenShare/weather/weather-script-output.png"


echo "================================================"                                          >> $LOG 2>&1
### Check Batterystate
NOTIFYBATTERY=0
CHECKBATTERY=`gasgauge-info -s | tr -d '%'`
echo "`date '+%Y-%m-%d_%H:%M:%S'` | Battery level: $CHECKBATTERY%"                               >> $LOG 2>&1
if [ ${CHECKBATTERY} -le 30 ] && [ ${NOTIFYBATTERY} -eq 0 ]; then
  NOTIFYBATTERY=1
  eips -f -g "$LIMGBATT"
  echo "`date '+%Y-%m-%d_%H:%M:%S'` | Critic battery level"                                      >> $LOG 2>&1
fi

if [ ${CHECKBATTERY} -gt 80 ]; then
  NOTIFYBATTERY=0
fi

if [ ${CHECKBATTERY} -le 10 ]; then
  eips -f -g "$LIMGBATT"
  echo "`date '+%Y-%m-%d_%H:%M:%S'` | Battery died"                                               >> $LOG 2>&1
  echo "mem" > /sys/power/state
fi 

lipc-set-prop com.lab126.powerd preventScreenSaver 1   #prevent screenSaver On
rm $LIMG
if wget -q "ftp://kindle:mario@$RIMG" -O "$LIMG"; then
  eips -f -g "$LIMG"
  echo "`date '+%Y-%m-%d_%H:%M:%S'` | New image downaloded and displayed"                          >> $LOG 2>&1
else
  eips -f -g "$LIMGERR"
  echo "`date '+%Y-%m-%d_%H:%M:%S'` | Error while displaying an image"                             >> $LOG 2>&1
fi