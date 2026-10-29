#!/bin/sh


NAME=display-weather
SCRIPTDIR="/mnt/us/weather"
LOG="$SCRIPTDIR/$NAME.log"

LIMG="$SCRIPTDIR/weather-script-output.png"
LIMGERR="$SCRIPTDIR/weather-error.png"
LIMGBATT="$SCRIPTDIR/weather-battery.png"
CONFIG="/var/local/meteo-to-kindle/credentials"

RIMG="192.168.1.125/OpenShare/weather/weather-script-output.png"
FTPHOST=${RIMG%%/*}
NETRC="/var/local/meteo-to-kindle/netrc"

# Cron never sees stderr: surface any failure on the e-ink display so the
# screen stops implying the last forecast is current.
fail_early() {  # $* = failure reason
  eips -f -g "$LIMGERR"
  echo "`date '+%Y-%m-%d_%H:%M:%S'` | $*" >> "$LOG" 2>&1
  echo "$*" >&2
  exit 1
}

if [ ! -r "$CONFIG" ]; then
  fail_early "Missing readable credentials file: $CONFIG"
fi

# The file is sourced as shell code: a more permissive file or directory
# would let another account replace it with commands this script executes.
# Fail closed unless the documented deployment modes are exact (600/700)
# and both paths are owned by the user running the script.
ME=$(id -un)
FILESTAT=$(ls -ld -- "$CONFIG" 2>/dev/null | awk '{print $1, $3}')
DIRSTAT=$(ls -ld -- "${CONFIG%/*}" 2>/dev/null | awk '{print $1, $3}')
if [ "$FILESTAT" != "-rw------- $ME" ]; then
  fail_early "Credentials file must be owned by $ME with mode 600: $CONFIG"
fi
if [ "$DIRSTAT" != "drwx------ $ME" ]; then
  fail_early "Credentials directory must be owned by $ME with mode 700: ${CONFIG%/*}"
fi
if ! sh -n "$CONFIG"; then
  fail_early "Invalid shell syntax in credentials file: $CONFIG"
fi
. "$CONFIG"
if [ -z "${FTP_USER:-}" ] || [ -z "${FTP_PASSWORD:-}" ]; then
  fail_early "FTP_USER and FTP_PASSWORD must be set in $CONFIG"
fi

# Keep the password off wget's command line (visible in `ps` output) by
# handing wget a netrc file regenerated in the same protected directory.
# The credentials file stays the single source of truth. Requires the GNU
# wget that recent Kindle firmware ships (--netrc-file, since 1.16).
# Values are always quoted and escaped: wget's netrc parser strips quotes
# and honours backslash escapes (netrc.c), which also keeps credentials
# containing spaces, quotes or backslashes intact.
encode() {  # $* = value -> quoted, escaped netrc token on stdout
  printf '"%s"' "$(printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g')"
}
netrc_line="machine $(encode "$FTPHOST") login $(encode "$FTP_USER") password $(encode "$FTP_PASSWORD")"
printf '%s\n' "$netrc_line" > "$NETRC"
chmod 600 "$NETRC"

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
if wget -q --netrc-file="$NETRC" "ftp://$RIMG" -O "$LIMG"; then
  eips -f -g "$LIMG"
  echo "`date '+%Y-%m-%d_%H:%M:%S'` | New image downaloded and displayed"                          >> $LOG 2>&1
else
  eips -f -g "$LIMGERR"
  echo "`date '+%Y-%m-%d_%H:%M:%S'` | Error while displaying an image"                             >> $LOG 2>&1
fi
