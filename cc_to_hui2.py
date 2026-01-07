import time
from dataclasses import dataclass
import mido

@dataclass
class FaderState:
    touched: bool = False
    last_move_ts: float = 0.0

FADER_CC_MAP = {
    0: 1,
    1: 11,
    2: 2,
    3: 21,
    4: 5,
    5: 3,
    6: 9,
    7: 7,
}

class CcToHui:
    """
    Translate MIDI CC (0-127) into HUI fader moves (14-bit) for Pro Tools.

    Defaults:
    - CC 7 (volume) on MIDI channels 1-8
    - Channel 1 -> HUI zone 0 (fader 1), ... channel 8 -> zone 7 (fader 8)
    """
    def __init__(
        self,
        in_port_name: str,
        out_port_name: str,
        cc_number: int = 7,
        release_after_ms: int = 250,
        poll_interval_ms: int = 10,
    ):
        self.in_port_name = in_port_name
        self.out_port_name = out_port_name
        self.cc_number = cc_number
        self.release_after = release_after_ms / 1000.0
        self.poll_interval = poll_interval_ms / 1000.0
        self.faders = [FaderState() for _ in range(8)]

        self.inport = mido.open_input(self.in_port_name)
        self.outport = mido.open_output(self.out_port_name)

    @staticmethod
    def _scale_7bit_to_14bit(v: int) -> int:
        v = max(0, min(127, v))
        return int(round(v * 16383 / 127))

    def _send_cc_ch1(self, controller: int, value: int):
        # HUI uses channel 1 CC messages (status 0xB0)
        msg = mido.Message("control_change", channel=0, control=controller, value=value)
        self.outport.send(msg)

    def _hui_touch(self, zone: int):
        # b0 0f 0z ; b0 2f 40
        self._send_cc_ch1(0x0F, zone & 0x7F)
        self._send_cc_ch1(0x2F, 0x40)

    def _hui_release(self, zone: int):
        # b0 0f 0z ; b0 2f 00
        self._send_cc_ch1(0x0F, zone & 0x7F)
        self._send_cc_ch1(0x2F, 0x00)

    def _hui_move(self, zone: int, value14: int):
        # b0 0z hi ; b0 2z lo
        value14 = max(0, min(16383, value14))
        hi = (value14 >> 7) & 0x7F
        lo = value14 & 0x7F
        self._send_cc_ch1(0x00 + zone, hi)
        self._send_cc_ch1(0x20 + zone, lo)

    def run(self):
    print("CC->HUI running")
    print(f"Input : {self.in_port_name}")
    print(f"Output: {self.out_port_name}")

    try:
        while True:
            now = time.time()

            for msg in self.inport.iter_pending():
                if msg.type != "control_change":
                    continue

                # MIDI channels 1–8 only
                if not (0 <= msg.channel <= 7):
                    continue

                zone = msg.channel

                if zone not in FADER_CC_MAP:
                    continue

                if msg.control != FADER_CC_MAP[zone]:
                    continue

                st = self.faders[zone]

                if not st.touched:
                    self._hui_touch(zone)
                    st.touched = True

                value14 = self._scale_7bit_to_14bit(msg.value)
                self._hui_move(zone, value14)
                st.last_move_ts = now

            # auto-release
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
        self.outport.close()
        print("Stopped")


if __name__ == "__main__":
    print("Available inputs:")
    for name in mido.get_input_names():
        print("  ", name)
    print("Available outputs:")
    for name in mido.get_output_names():
        print("  ", name)

    # EDIT THESE to match your system’s port names
    IN_PORT  = "Your CC Controller Input Port Name Here"
    OUT_PORT = "Your Virtual MIDI Port To Pro Tools Here"

    app = CcToHui(
        in_port_name=IN_PORT,
        out_port_name=OUT_PORT,
        cc_number=7,            # change if your hardware sends a different CC
        release_after_ms=250,   # tweak for smoother automation writes
    )
    app.run()
