# midi_cc_to_hui
# CC → HUI for Pro Tools (macOS)

Translate MIDI CC fader data (0–127) into **HUI fader moves** so **Pro Tools** can write **Volume automation** from a non-HUI MIDI controller.

This project is designed for macOS and Pro Tools Studio 2024.x. It uses:
- `mido` + `python-rtmidi` for MIDI I/O
- macOS **IAC Driver** as the virtual MIDI bridge into Pro Tools
- HUI fader messages (14-bit) for smooth automation writing

## What this does

- Listens to incoming MIDI **Control Change** messages from your controller
- Maps specific CC numbers (ex: CC1, CC11, CC7) to HUI faders 1–8
- Sends HUI fader moves to Pro Tools via an IAC virtual MIDI port
- Sends HUI **touch** on first movement and **release** after inactivity (so automation writes correctly)

## Requirements

- macOS 12+ (tested on macOS 15.x)
- Pro Tools Studio 2024.x
- Python 3.10+ (works with newer, including 3.13)
- Homebrew (recommended)
- A MIDI controller that outputs CC values (0–127)

---

# 1) Install Homebrew (if needed)

Open Terminal and run:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
````

Verify:

```bash
brew --version
```

---

# 2) Install Python (recommended via Homebrew)

macOS ships with an “externally managed” Python environment (PEP 668), so you should use a venv.

Install Python:

```bash
brew install python
```

Verify:

```bash
python3 --version
```

---

# 3) Create the IAC Driver virtual MIDI port

This is how the Python script “feeds” Pro Tools.

1. Open **Audio MIDI Setup**
2. Menu: **Window → Show MIDI Studio**
3. Double-click **IAC Driver**
4. Check **Device is online**
5. Add a port named (example): `CC_to_HUI`

You should now see this port in apps as:

* Input: `IAC Driver CC_to_HUI`
* Output: `IAC Driver CC_to_HUI`

---

# 4) Configure Pro Tools for HUI

In **Pro Tools**:

1. **Setup → Peripherals…**
2. Go to **MIDI Controllers**
3. Add one row:

   * **Type:** HUI
   * **Receive From:** `CC_to_HUI` (IAC)
   * **Send To:** `CC_to_HUI` (IAC)
   * **# Ch’s:** `8`

Automation tips:

* Put track automation mode to **Touch** or **Latch**
* Show **Volume** automation lane
* Press play/record as needed for writing

---

# 5) Set up the Python virtual environment (venv)

From your repo folder:

```bash
cd path/to/your/repo
python3 -m venv venv
source venv/bin/activate
```

Your prompt should show `(venv)`.

Install dependencies:

```bash
pip install mido python-rtmidi
```

---

# 6) Configure the script ports + mapping

## Choose your MIDI input device

The script prints available ports at startup. Use the exact name.

Example inputs might look like:

* `Sparrow 8x60`
* `Supernova II`
* `Breath Controller ...`

## Edit these values in `cc_to_hui.py`

```python
IN_PORT = "Your Controller Name Here"
OUT_PORT = "IAC Driver CC_to_HUI"
```

## CC mapping

The default is a CC-number-to-fader map for 8 faders:

```python
CC_TO_ZONE = {
    1: 0,
    11: 1,
    2: 2,
    21: 3,
    5: 4,
    3: 5,
    9: 6,
    7: 7,
}
```

Meaning:

* CC1 controls Pro Tools fader 1
* CC11 controls Pro Tools fader 2
* …
* CC7 controls Pro Tools fader 8

Change these CC numbers to match your hardware.

---

# 7) Compile check + run

## Syntax check (no output = good)

```bash
python -m py_compile cc_to_hui.py
```

## Run

```bash
python cc_to_hui.py
```

You should see:

* available MIDI input/output port names
* “CC->HUI running”
* your mapping printed

Move a controller fader and you should see Pro Tools volume faders respond.

Stop with:

* `Ctrl + C`

---

# Troubleshooting

## “OSError: unknown port '...’”

Your `IN_PORT` or `OUT_PORT` string does not exactly match a real port name.
Run the script and copy/paste the name from “Available inputs/outputs”.

## Only fader 1 works

Your controller likely sends all faders on the same MIDI channel.
This project maps by **CC number**, so make sure your other faders send distinct CCs.
Temporarily add this inside the MIDI loop to see what’s coming in:

```python
print(msg)
```

Move each fader once and update `CC_TO_ZONE` accordingly.

## Pro Tools faders move but no automation writes

* Track must be in **Touch/Latch**
* Make sure you are viewing/writing **Volume** automation
* Ensure playback is rolling

## Terminal does not see MIDI devices (macOS privacy)

System Settings → **Privacy & Security**

* Enable relevant permissions for your Terminal app if needed

---

# Run on login (optional)

You can run this script automatically at login using `launchd` or a small wrapper script.
If you want, open an issue or PR request and include:

* your repo path
* desired port names
* whether you want it to auto-start only when Pro Tools is running

---
