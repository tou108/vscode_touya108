#!/usr/bin/env python3
"""
Nintendo Switch Pro Controller Bluetooth HID Emulator
------------------------------------------------------
Electron の main プロセスから child_process として起動される。
stdin: JSON コマンド (1行1コマンド)
stdout: JSON イベント (1行1イベント)

必要パッケージ: pip install pybluez
Windows の場合: https://github.com/pybluez/pybluez を参照
"""

import sys
import json
import socket
import struct
import threading
import time
import os

# ─────────────────────────────────────────
#  Pro Controller HID descriptor (完全版)
# ─────────────────────────────────────────
PRO_CONTROLLER_HID_DESCRIPTOR = bytes([
    0x05,0x01,0x09,0x05,0xa1,0x01,0x15,0x00,0x25,0x01,0x35,0x00,0x45,0x01,0x75,0x01,
    0x95,0x10,0x05,0x09,0x19,0x01,0x29,0x10,0x81,0x02,0x05,0x01,0x25,0x07,0x46,0x3b,
    0x01,0x75,0x04,0x95,0x01,0x65,0x14,0x09,0x39,0x81,0x42,0x65,0x00,0x95,0x01,0x81,
    0x01,0x26,0xff,0x00,0x46,0xff,0x00,0x09,0x30,0x09,0x31,0x09,0x32,0x09,0x35,0x75,
    0x08,0x95,0x04,0x81,0x02,0x06,0x00,0xff,0x09,0x20,0x09,0x21,0x09,0x22,0x09,0x23,
    0x09,0x24,0x09,0x25,0x09,0x26,0x09,0x27,0x09,0x28,0x09,0x29,0x09,0x2a,0x09,0x2b,
    0x95,0x0d,0x81,0x02,0xc0,
])

# ─────────────────────────────────────────
#  SPI フラッシュ (工場キャリブレーション)
# ─────────────────────────────────────────
SPI_FLASH = bytearray(0x10000)
# ユーザースティックキャリブレーション (6軸センサーなし)
SPI_FLASH[0x8010:0x8010+0x18] = bytes([
    0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,
    0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,
    0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff,
])
# 工場スティックキャリブレーション
SPI_FLASH[0x603d:0x603d+0x12] = bytes([
    0xbe,0xff,0xf8,0xb8,0xbb,0x7d,0xf3,0xd4,0x14,
    0x35,0x54,0x17,0x26,0x85,0x3b,0xa9,0xc7,0x2d,
])
SPI_FLASH[0x6046:0x6046+0x0d] = bytes([
    0x0f,0x30,0x61,0x96,0x30,0xf3,0xd4,0x14,
    0x35,0x54,0x17,0x26,0x85,
])
# IMU キャリブレーション
SPI_FLASH[0x6020:0x6020+0x18] = bytes([
    0x75,0xff,0xd0,0xff,0x25,0x00,0x22,0x00,
    0xdd,0xff,0xf0,0xff,0x0b,0x01,0xf0,0xff,
    0xd6,0xff,0x3b,0x34,0x3b,0x34,0x3b,0x34,
])
# デバイスカラー
SPI_FLASH[0x6050:0x6050+0x06] = bytes([0x32,0x32,0x32,0xff,0xff,0xff])

# ─────────────────────────────────────────
#  ボタンビットマップ
# ─────────────────────────────────────────
# byte_idx, bit
BUTTON_MAP = {
    'Y':            (0, 0), 'X':           (0, 1), 'B':          (0, 2), 'A':       (0, 3),
    'RIGHT_SR':     (0, 4), 'RIGHT_SL':    (0, 5), 'R':          (0, 6), 'ZR':      (0, 7),
    'MINUS':        (1, 0), 'PLUS':        (1, 1), 'RIGHT_STICK':(1, 2), 'LEFT_STICK':(1, 3),
    'HOME':         (1, 4), 'CAPTURE':     (1, 5),
    'DOWN':         (2, 0), 'UP':          (2, 1), 'RIGHT':       (2, 2), 'LEFT':    (2, 3),
    'LEFT_SR':      (2, 4), 'LEFT_SL':     (2, 5), 'L':          (2, 6), 'ZL':      (2, 7),
}

def log(data: dict):
    """stdout へ JSON イベントを送信"""
    try:
        print(json.dumps(data, ensure_ascii=False), flush=True)
    except Exception:
        pass

def err(msg: str):
    log({'type': 'error', 'msg': msg})

def info(msg: str):
    log({'type': 'info', 'msg': msg})

def status(s: str, **kwargs):
    log({'type': 'status', 'status': s, **kwargs})


class ProController:
    """Nintendo Switch Pro Controller Bluetooth HID エミュレーター"""

    HID_CONTROL_PSM  = 0x11
    HID_INTERRUPT_PSM = 0x13

    # デバイス情報
    BT_NAME        = 'Pro Controller'
    FIRMWARE_VER   = (3, 72)   # FW 3.72
    DEVICE_TYPE    = 0x03      # Pro Controller
    MAC_ADDRESS    = bytes([0x98, 0xa1, 0x70, 0x00, 0x00, 0x00])  # 後で上書き

    def __init__(self, switch_mac: str, local_mac: str = ''):
        self.switch_mac = switch_mac.upper().replace('-', ':')
        self.local_mac  = local_mac.upper().replace('-', ':') if local_mac else ''

        self._ctrl_sock  = None
        self._intr_sock  = None
        self._connected  = False
        self._running    = False

        # ボタン・スティック状態
        self._buttons = bytearray(3)   # [右ボタン, 共通, 左ボタン]
        self._lstick  = bytearray(3)   # 12bit x/y packed
        self._rstick  = bytearray(3)
        self._set_stick_center(self._lstick)
        self._set_stick_center(self._rstick)

        self._timer = 0
        self._pkt_lock = threading.Lock()
        self._send_lock = threading.Lock()

        # 入力レポート送信タスク
        self._report_thread: threading.Thread | None = None

    # ──────────────────────────────────────
    #  スティック補助
    # ──────────────────────────────────────
    def _set_stick_center(self, buf):
        x, y = 0x800, 0x800
        buf[0] = x & 0xff
        buf[1] = ((x >> 8) & 0x0f) | ((y & 0x0f) << 4)
        buf[2] = (y >> 4) & 0xff

    def _set_stick(self, buf, x: int, y: int):
        """x, y: 0-4095 (センター=2048)"""
        x = max(0, min(4095, x))
        y = max(0, min(4095, y))
        buf[0] = x & 0xff
        buf[1] = ((x >> 8) & 0x0f) | ((y & 0x0f) << 4)
        buf[2] = (y >> 4) & 0xff

    # ──────────────────────────────────────
    #  公開 API (外部スレッドから呼ぶ)
    # ──────────────────────────────────────
    def press_button(self, name: str, pressed: bool):
        if name not in BUTTON_MAP:
            return
        b_idx, bit = BUTTON_MAP[name]
        with self._pkt_lock:
            if pressed:
                self._buttons[b_idx] |= (1 << bit)
            else:
                self._buttons[b_idx] &= ~(1 << bit)

    def set_stick(self, side: str, x: int, y: int):
        with self._pkt_lock:
            if side == 'L':
                self._set_stick(self._lstick, x, y)
            else:
                self._set_stick(self._rstick, x, y)

    def reset_all(self):
        with self._pkt_lock:
            self._buttons = bytearray(3)
            self._set_stick_center(self._lstick)
            self._set_stick_center(self._rstick)

    # ──────────────────────────────────────
    #  接続
    # ──────────────────────────────────────
    def connect(self):
        self._running = True
        try:
            info(f'Switch ({self.switch_mac}) へ接続中...')
            self._ctrl_sock = socket.socket(
                socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP)
            self._ctrl_sock.settimeout(10)
            self._ctrl_sock.connect((self.switch_mac, self.HID_CONTROL_PSM))

            self._intr_sock = socket.socket(
                socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP)
            self._intr_sock.settimeout(10)
            self._intr_sock.connect((self.switch_mac, self.HID_INTERRUPT_PSM))

            self._intr_sock.settimeout(None)
            self._connected = True
            status('connected', mac=self.switch_mac)
            info('Switch に接続しました！')
        except OSError as e:
            err(f'接続失敗: {e}')
            status('disconnected')
            self._cleanup()
            return

        # 入力レポート送信スレッド
        self._report_thread = threading.Thread(target=self._report_loop, daemon=True)
        self._report_thread.start()

        # Switch からのコマンド受信
        self._recv_loop()

    def disconnect(self):
        self._running = False
        self._connected = False
        self._cleanup()
        status('disconnected')
        info('切断しました')

    def _cleanup(self):
        for s in [self._intr_sock, self._ctrl_sock]:
            try:
                if s:
                    s.close()
            except Exception:
                pass
        self._intr_sock = None
        self._ctrl_sock = None

    # ──────────────────────────────────────
    #  受信ループ (OUTPUT report from Switch)
    # ──────────────────────────────────────
    def _recv_loop(self):
        while self._running and self._connected:
            try:
                data = self._intr_sock.recv(256)
                if not data:
                    break
                self._handle_output(data)
            except OSError:
                break
        self.disconnect()

    def _handle_output(self, data: bytes):
        if len(data) < 2:
            return
        # HID output report: data[0]=0xa2 (HID type), data[1]=report_id, data[2]=subcommand
        report_id = data[1] if len(data) > 1 else 0
        if report_id in (0x01, 0x10, 0x11):  # subcommand / NFC / etc.
            if len(data) >= 3:
                self._handle_subcommand(data[2], data[3:] if len(data) > 3 else b'')

    def _handle_subcommand(self, cmd: int, args: bytes):
        # 各サブコマンドへの応答
        if cmd == 0x00:   # NOP
            self._ack_subcommand(cmd)
        elif cmd == 0x01: # Bluetooth manual pairing
            self._ack_subcommand(cmd)
        elif cmd == 0x02: # Request device info
            self._reply_device_info()
        elif cmd == 0x03: # Set input report mode
            self._ack_subcommand(cmd)
        elif cmd == 0x04: # Trigger buttons elapsed time
            self._ack_subcommand(cmd)
        elif cmd == 0x08: # Set shipment
            self._ack_subcommand(cmd)
        elif cmd == 0x10: # SPI flash read
            self._reply_spi_read(args)
        elif cmd == 0x11: # SPI flash write
            self._ack_subcommand(cmd)
        elif cmd == 0x21: # NFC/IR MCU config
            self._ack_subcommand(cmd)
        elif cmd == 0x22: # NFC/IR MCU state
            self._ack_subcommand(cmd)
        elif cmd == 0x24: # Reset NFC/IR MCU
            self._ack_subcommand(cmd)
        elif cmd == 0x30: # Set player lights
            self._ack_subcommand(cmd)
        elif cmd == 0x38: # Set HOME light
            self._ack_subcommand(cmd)
        elif cmd == 0x40: # Enable 6-axis sensor
            self._ack_subcommand(cmd)
        elif cmd == 0x41: # Set 6-axis sensor sensitivity
            self._ack_subcommand(cmd)
        elif cmd == 0x43: # Get regulated voltage
            self._ack_subcommand(cmd)
        elif cmd == 0x48: # Enable vibration
            self._ack_subcommand(cmd)
        else:
            self._ack_subcommand(cmd)

    def _build_input_report(self, subcommand_reply: bytes = b'') -> bytes:
        """0x21 (subcommand reply) or 0x30 (standard full) input report"""
        with self._pkt_lock:
            b = bytearray(self._buttons)
            ls = bytearray(self._lstick)
            rs = bytearray(self._rstick)

        self._timer = (self._timer + 1) & 0xff
        timer = self._timer

        if subcommand_reply:
            report = bytearray(50)
            report[0] = 0x21          # report ID
            report[1] = timer
            report[2] = 0x8e          # battery + connection info
            report[3] = b[0]; report[4] = b[1]; report[5] = b[2]
            report[6] = ls[0]; report[7] = ls[1]; report[8] = ls[2]
            report[9] = rs[0]; report[10] = rs[1]; report[11] = rs[2]
            report[12] = 0x00         # vibration ack
            report[13:13+len(subcommand_reply)] = subcommand_reply
        else:
            report = bytearray(50)
            report[0] = 0x30
            report[1] = timer
            report[2] = 0x8e
            report[3] = b[0]; report[4] = b[1]; report[5] = b[2]
            report[6] = ls[0]; report[7] = ls[1]; report[8] = ls[2]
            report[9] = rs[0]; report[10] = rs[1]; report[11] = rs[2]
            report[12] = 0x00
            # IMU placeholder (zeros OK for basic operation)

        return bytes([0xa1]) + bytes(report)

    def _send_input(self, payload: bytes):
        if not self._connected or not self._intr_sock:
            return
        with self._send_lock:
            try:
                self._intr_sock.sendall(payload)
            except OSError:
                pass

    def _ack_subcommand(self, cmd: int, extra: bytes = b''):
        reply = bytes([0x80 | (cmd & 0x7f), 0x00]) + extra
        payload = self._build_input_report(reply)
        self._send_input(payload)

    def _reply_device_info(self):
        mac = self.MAC_ADDRESS
        reply = bytes([
            0x82, 0x02,       # ACK + subcommand 0x02
            self.FIRMWARE_VER[0], self.FIRMWARE_VER[1],  # FW ver
            self.DEVICE_TYPE,
            0x02,             # unknown
            mac[0], mac[1], mac[2], mac[3], mac[4], mac[5],
            0x01,             # is Pro Controller
            0x02,             # unknown
        ])
        payload = self._build_input_report(reply)
        self._send_input(payload)

    def _reply_spi_read(self, args: bytes):
        if len(args) < 5:
            self._ack_subcommand(0x10)
            return
        addr = struct.unpack_from('<I', args, 0)[0]
        length = args[4]
        data = SPI_FLASH[addr:addr + length]
        reply = bytes([0x90, 0x10]) + struct.pack('<I', addr) + bytes([length]) + bytes(data)
        payload = self._build_input_report(reply)
        self._send_input(payload)

    # ──────────────────────────────────────
    #  定期入力レポート送信 (~60Hz)
    # ──────────────────────────────────────
    def _report_loop(self):
        interval = 1.0 / 60.0
        while self._running and self._connected:
            payload = self._build_input_report()
            self._send_input(payload)
            time.sleep(interval)


# ─────────────────────────────────────────
#  stdin コマンドループ
# ─────────────────────────────────────────
_controller: ProController | None = None
_connect_thread: threading.Thread | None = None


def handle_command(cmd: dict):
    global _controller, _connect_thread

    t = cmd.get('type')

    if t == 'connect':
        mac = cmd.get('mac', '').strip()
        if not mac:
            err('MAC アドレスが空です')
            return
        if _controller and _controller._connected:
            err('既に接続中です')
            return
        _controller = ProController(mac)
        _connect_thread = threading.Thread(target=_controller.connect, daemon=True)
        _connect_thread.start()

    elif t == 'disconnect':
        if _controller:
            _controller.disconnect()

    elif t == 'button':
        if _controller and _controller._connected:
            _controller.press_button(cmd.get('name', ''), bool(cmd.get('pressed', False)))

    elif t == 'stick':
        if _controller and _controller._connected:
            _controller.set_stick(cmd.get('side', 'L'), int(cmd.get('x', 2048)), int(cmd.get('y', 2048)))

    elif t == 'reset':
        if _controller:
            _controller.reset_all()

    elif t == 'ping':
        log({'type': 'pong'})

    else:
        err(f'不明なコマンド: {t}')


def main():
    info('Switch BT コントローラー バックエンド起動')
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            cmd = json.loads(line)
            handle_command(cmd)
        except json.JSONDecodeError as e:
            err(f'JSON パースエラー: {e}')
        except Exception as e:
            err(f'エラー: {e}')


if __name__ == '__main__':
    main()
