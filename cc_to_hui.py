import time
from dataclasses import dataclass

import mido


@dataclass
class FaderState:
    touched: bool = False
    last_move_ts: float = 0.0


# Map incoming CC -> HUI fader zone (0-7).
# Expected (per your description):
# 1=CC1 (mod), 2=CC11 (expr), 3=CC2 (breath), 4=CC21, 5=CC5 (porta rate),
# 6=CC3, 7=CC9, 8=CC7 (volume)
#
# If your Sparrow actually has CC1/CC11 swapped, swap the first two entries.
CC_TO_ZONE = {
    11: 0,
    1: 1,
    2: 2,
    21: 3,
    5: 4,
    3: 5,
    9: 6,
    7: 7,
}

# Supernova II port name and CC mapping for navigation controls.
# Choose CCs that your Supernova can send reliably as "buttons" (0/127 is ideal).
SUPERNOVA_PORT = "Supernova II"
BANK_RIGHT_CC = 75
BANK_LEFT_CC = 76
CHAN_RIGHT_CC = 77
CHAN_LEFT_CC = 78


class CcToHui:
    """
    Translate incoming MIDI CC (0-127) into HUI fader moves (14-bit) for Pro Tools.

    Inputs:
    - Sparrow (or other): CC messages mapped via CC_TO_ZONE -> HUI faders 1-8
    - Supernova II (optional): CC triggers for bank/channel navigation

    Output:
    - HUI messages to the selected output port (IAC) on MIDI channel 1 (mido channel=0)
    """

    def __init__(
        self,
        in_port_name: str,
        out_port_name: str,
        supernova_port_name: str | None = SUPERNOVA_PORT,
        release_after_ms: int = 250,
        poll_interval_ms: int = 10,
        restrict_to_channels_1_to_8: bool = False,
        nav_on_nonzero_value: bool = True,
    ) -> None:
        self.in_port_name = in_port_name
        self.out_port_name = out_port_name
        self.supernova_port_name = supernova_port_name

        self.release_after = release_after_ms / 1000.0
        self.poll_interval = poll_interval_ms / 1000.0
        self.restrict_to_channels_1_to_8 = restrict_to_channels_1_to_8
        self.nav_on_nonzero_value = nav_on_nonzero_value

        self.faders = [FaderState() for _ in range(8)]

        # Primary input (Sparrow faders)
        self.inport = mido.open_input(self.in_port_name)

        # Optional second input (Supernova navigation)
        self.ctrlport = None
        if self.supernova_port_name:
            self.ctrlport = mido.open_input(self.supernova_port_name)

        # Output to Pro Tools HUI (IAC)
        self.outport = mido.open_output(self.out_port_name)

    @staticmethod
    def _scale_7bit_to_14bit(v: int) -> int:
        v = max(0, min(127, int(v)))
        return int(round(v * 16383 / 127))

    def _send_cc_hui(self, controller: int, value: int) -> None:
        # HUI uses CC on MIDI channel 1 (status 0xB0). In mido: channel=0.
        msg = mido.Message(
            "control_change",
            channel=0,
            control=int(controller) & 0x7F,
            value=int(value) & 0x7F,
        )
        self.outport.send(msg)

    # ----- HUI fader -----

    def _hui_touch(self, zone: int) -> None:
        # Touch fader z: B0 0F 0z, then B0 2F 40
        self._send_cc_hui(0x0F, zone & 0x7F)
        self._send_cc_hui(0x2F, 0x40)

    def _hui_release(self, zone: int) -> None:
        # Release fader z: B0 0F 0z, then B0 2F 00
        self._send_cc_hui(0x0F, zone & 0x7F)
        self._send_cc_hui(0x2F, 0x00)

    def _hui_move(self, zone: int, value14: int) -> None:
        # Move fader z (14-bit): B0 0z hi, then B0 2z lo
        value14 = max(0, min(16383, int(value14)))
        hi = (value14 >> 7) & 0x7F
        lo = value14 & 0x7F
        self._send_cc_hui(0x00 + zone, hi)
        self._send_cc_hui(0x20 + zone, lo)

    # ----- HUI navigation button press -----

    def _hui_press_button(self, zone: int, port: int) -> None:
        """
        Press + release a HUI button.
        - zone select: B0 0C zz
        - port on:     B0 2C 4p
        - port off:    B0 2C 0p
        """
        port = port & 0x07
        self._send_cc_hui(0x0C, zone & 0x7F)          # tx (zone select)
        self._send_cc_hui(0x2C, 0x40 | port)          # on
        self._send_cc_hui(0x2C, port)                 # off

    def _handle_supernova_msg(self, msg: mido.Message) -> None:
        if msg.type != "control_change":
            return

        if self.nav_on_nonzero_value and msg.value == 0:
            return

        # HUI "channel selection" zone 0x0A ports:
        # 0: channel left, 1: bank left, 2: channel right, 3: bank right
        if msg.control == BANK_RIGHT_CC:
            self._hui_press_button(0x0A, 3)
        elif msg.control == BANK_LEFT_CC:
            self._hui_press_button(0x0A, 1)
        elif msg.control == CHAN_RIGHT_CC:
            self._hui_press_button(0x0A, 2)
        elif msg.control == CHAN_LEFT_CC:
            self._hui_press_button(0x0A, 0)

    def run(self) -> None:
        print("CC->HUI running")
        print(f"Primary input : {self.in_port_name}")
        print(f"Ctrl input    : {self.supernova_port_name if self.ctrlport else '(none)'}")
        print(f"Output        : {self.out_port_name}")
        print(f"CC_TO_ZONE    : {CC_TO_ZONE}")
        print(
            "Supernova CCs : "
            f"bank<={BANK_LEFT_CC} bank=>{BANK_RIGHT_CC} "
            f"chan<={CHAN_LEFT_CC} chan=>{CHAN_RIGHT_CC}"
        )

        try:
            while True:
                now = time.time()

                # Sparrow faders -> HUI faders
                for msg in self.inport.iter_pending():
                    if msg.type != "control_change":
                        continue

                    # Optional guard if you want to ignore other channels
                    if self.restrict_to_channels_1_to_8 and not (0 <= msg.channel <= 7):
                        continue

                    zone = CC_TO_ZONE.get(msg.control)
                    if zone is None:
                        continue

                    st = self.faders[zone]

                    if not st.touched:
                        self._hui_touch(zone)
                        st.touched = True

                    value14 = self._scale_7bit_to_14bit(msg.value)
                    self._hui_move(zone, value14)
                    st.last_move_ts = now

                # Supernova navigation controls
                if self.ctrlport is not None:
                    for msg in self.ctrlport.iter_pending():
                        self._handle_supernova_msg(msg)

                # Auto-release after inactivity
                for zone, st in enumerate(self.faders):
                    if st.touched and st.last_move_ts > 0 and (now - st.last_move_ts) >= self.release_after:
                        self._hui_release(zone)
                        st.touched = False
                        st.last_move_ts = 0.0

                time.sleep(self.poll_interval)

        except KeyboardInterrupt:
            pass

        finally:
            for zone, st in enumerate(self.faders):
                if st.touched:
                    self._hui_release(zone)

            self.inport.close()
            if self.ctrlport is not None:
                self.ctrlport.close()
            self.outport.close()
            print("Stopped")


def main() -> None:
    print("Available inputs:")
    for name in mido.get_input_names():
        print("  ", name)

    print("Available outputs:")
    for name in mido.get_output_names():
        print("  ", name)

    IN_PORT = "Sparrow 8x60"
    OUT_PORT = "IAC Driver CC_to_HUI"

    app = CcToHui(
        in_port_name=IN_PORT,
        out_port_name=OUT_PORT,
        supernova_port_name=SUPERNOVA_PORT,  # set to None to disable Supernova controls
        release_after_ms=250,
        poll_interval_ms=10,
        restrict_to_channels_1_to_8=False,
        nav_on_nonzero_value=True,
    )
    app.run()


if __name__ == "__main__":
    main()
