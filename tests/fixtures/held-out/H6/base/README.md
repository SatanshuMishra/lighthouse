# hearthctl

hearthctl controls a home thermostat connected to this computer over USB serial, and plans its daily heating programme.

## Use

    python3 -m hearthctl status
    python3 -m hearthctl set 21.5
    python3 -m hearthctl plan 06:30=20 22:00=16 08:00=18

`status` prints the room temperature the thermostat reads and `set` changes its target; both need the thermostat plugged in. hearthctl talks to the serial port the `HEARTH_PORT` environment variable names, by default `/dev/cu.usbmodem-hearth`, and exits 3 when no thermostat is there. `plan` needs no thermostat: it prints the programme's slots in time order.

The thermostat answers one text command per line: `TEMP?`, `SET <celsius>` and `BOOST <seconds>`.

## Tests

The tests replace the serial link with a fake one, so they run without a thermostat. Run them from the repository root with:

    python3 -m unittest discover -s tests
