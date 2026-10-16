# inkstrip

inkstrip prints address and parcel labels on a thermal label printer connected to this computer over USB serial, and previews how a label will be laid out.

## Use

    python3 -m inkstrip preview "Mira Okafor" "12 Quay Street"
    python3 -m inkstrip print "Mira Okafor" "12 Quay Street"
    python3 -m inkstrip sheet labels.txt
    python3 -m inkstrip feed
    python3 -m inkstrip status

Each argument is one row of the label. A row longer than 24 characters wraps onto the next line, and a label holds at most 4 lines.

`preview` needs no printer: it prints the label's lines inside a frame the size of the label. `print` prints the label onto the blank label under the print head, `feed` advances the strip by one label (28 mm, a 25 mm label and the 3 mm gap after it), and `status` prints what the printer reports. `sheet` prints every label in a file in one run, one label after another, each on its own label, and prints how many it printed. In the file, each label is a block of rows and a blank line separates one label from the next. Every label is laid out before anything is sent, so a label that does not fit stops the run before the first one prints. These four need the printer plugged in.

inkstrip talks to the serial port the `INKSTRIP_PORT` environment variable names, by default `/dev/cu.usbserial-inkstrip`. It exits 3 when no printer is there and 2 when a label does not fit.

The printer answers one text command per line: `STATUS?`, `TEXT <line>` to add a line to the label it is building, `PRINT` to print those lines onto the label under the head, and `FEED <mm>` to advance the strip.

## Tests

The tests replace the serial link with a fake one, so they run without a printer. Run them from the repository root with:

    python3 -m unittest discover -s tests
