import asyncio
import json
import sys
import threading

from bleak import BleakClient, BleakScanner
from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QKeySequence
from PyQt6.QtWidgets import (
	QApplication,
	QColorDialog,
	QComboBox,
	QFrame,
	QGridLayout,
	QHBoxLayout,
	QLabel,
	QPlainTextEdit,
	QPushButton,
	QSizePolicy,
	QVBoxLayout,
	QWidget,
)


DEVICE_NAME = "NanoESP32-Lights"
SERVICE_UUID = "a3f8e58e-fdfe-4af9-95a0-d523dac030c5"
CHARACTERISTIC_UUID = "0de4cb4f-9d0f-4e4d-a6dd-49fbd2dc6b4a"
DEFAULT_LED_COLORS = [
	"#ff3b30",
	"#ff9500",
	"#ffcc00",
	"#34c759",
	"#00c7be",
	"#32ade6",
	"#007aff",
	"#5856d6",
	"#af52de",
	"#ff2d55",
]
ANIMATIONS = ["static", "train", "random colors"]


class LedButton(QPushButton):
	color_changed = pyqtSignal(int, str)

	def __init__(self, index: int, color_hex: str, parent: QWidget | None = None) -> None:
		super().__init__(parent)
		self.index = index
		self.color_hex = color_hex
		self.setFixedSize(42, 42)
		self.setCursor(Qt.CursorShape.PointingHandCursor)
		self.clicked.connect(self.choose_color)
		self._apply_style()

	def choose_color(self) -> None:
		selected_color = QColorDialog.getColor(QColor(self.color_hex), self, "Choose LED color")
		if not selected_color.isValid():
			return

		self.color_hex = selected_color.name()
		self._apply_style()
		self.color_changed.emit(self.index, self.color_hex)

	def _apply_style(self) -> None:
		self.setStyleSheet(
			f"""
			QPushButton {{
				background-color: {self.color_hex};
				border: 2px solid #1f1f1f;
				border-radius: 21px;
			}}
			QPushButton:hover {{
				border-color: #ffffff;
			}}
			"""
		)


class BleController(QObject):
	log_message = pyqtSignal(str)
	connection_changed = pyqtSignal(bool)

	def __init__(self) -> None:
		super().__init__()
		self.loop: asyncio.AbstractEventLoop | None = None
		self.thread: threading.Thread | None = None
		self.client: BleakClient | None = None

	def ensure_started(self) -> None:
		if self.thread and self.thread.is_alive():
			return

		self.thread = threading.Thread(target=self._run_event_loop, daemon=True)
		self.thread.start()

	def _run_event_loop(self) -> None:
		self.loop = asyncio.new_event_loop()
		asyncio.set_event_loop(self.loop)
		self.loop.run_forever()

	def connect_to_device(self) -> None:
		self.ensure_started()
		self._submit(self._connect_to_device())

	def send_payload(self, payload: str) -> None:
		self.ensure_started()
		self._submit(self._write_payload(payload))

	def stop(self) -> None:
		if not self.loop:
			return

		future = asyncio.run_coroutine_threadsafe(self._disconnect(), self.loop)
		try:
			future.result(timeout=5)
		except Exception:
			pass
		self.loop.call_soon_threadsafe(self.loop.stop)

	def _submit(self, coroutine: asyncio.coroutines) -> None:
		if not self.loop:
			self.log_message.emit("BLE worker is not ready yet.")
			return
		asyncio.run_coroutine_threadsafe(coroutine, self.loop)

	async def _connect_to_device(self) -> None:
		if self.client and self.client.is_connected:
			self.log_message.emit("Already connected to the Arduino.")
			self.connection_changed.emit(True)
			return

		self.log_message.emit(f"Scanning for {DEVICE_NAME} over BLE...")

		try:
			devices = await BleakScanner.discover(timeout=5.0)
		except Exception as exc:
			self.log_message.emit(f"BLE scan failed: {exc}")
			return

		target_device = next((device for device in devices if device.name == DEVICE_NAME), None)
		if not target_device:
			self.log_message.emit("Arduino was not found. Make sure it is advertising.")
			self.connection_changed.emit(False)
			return

		self.log_message.emit(f"Found device: {target_device.name} ({target_device.address})")
		self.client = BleakClient(target_device, disconnected_callback=self._handle_disconnect)

		try:
			await self.client.connect()
		except Exception as exc:
			self.log_message.emit(f"Connection failed: {exc}")
			self.connection_changed.emit(False)
			self.client = None
			return

		self.log_message.emit("BLE connection established.")
		self.connection_changed.emit(True)

	async def _write_payload(self, payload: str) -> None:
		if not self.client or not self.client.is_connected:
			self.log_message.emit("Connect to the Arduino before sending updates.")
			self.connection_changed.emit(False)
			return

		try:
			await self.client.write_gatt_char(CHARACTERISTIC_UUID, payload.encode("utf-8"), response=True)
		except Exception as exc:
			self.log_message.emit(f"Write failed: {exc}")
			return

		self.log_message.emit(f"Sent payload: {payload}")

	async def _disconnect(self) -> None:
		if self.client and self.client.is_connected:
			await self.client.disconnect()
		self.client = None
		self.connection_changed.emit(False)

	def _handle_disconnect(self, _client: BleakClient) -> None:
		self.client = None
		self.log_message.emit("BLE device disconnected.")
		self.connection_changed.emit(False)


class LedControllerWindow(QWidget):
	def __init__(self) -> None:
		super().__init__()
		self.ble_controller = BleController()
		self.ble_controller.log_message.connect(self.append_log)
		self.ble_controller.connection_changed.connect(self.on_connection_changed)

		self.led_colors = list(DEFAULT_LED_COLORS)
		self.selected_key = "None"
		self.capture_key_mode = False
		self.is_connected = False

		self.setWindowTitle("Lights Controller")
		self.resize(920, 420)
		self._build_ui()

	def _build_ui(self) -> None:
		root_layout = QVBoxLayout(self)
		root_layout.setContentsMargins(20, 20, 20, 20)
		root_layout.setSpacing(16)

		title = QLabel("BLE Light Strip Controller")
		title.setStyleSheet("font-size: 26px; font-weight: 700;")
		root_layout.addWidget(title)

		top_row = QHBoxLayout()
		top_row.setSpacing(12)

		self.connect_button = QPushButton("Start BLE communication")
		self.connect_button.clicked.connect(self.start_ble_communication)
		self.connect_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
		top_row.addWidget(self.connect_button)

		self.connection_label = QLabel("Status: disconnected")
		top_row.addWidget(self.connection_label)
		top_row.addStretch(1)
		root_layout.addLayout(top_row)

		led_frame = QFrame()
		led_frame.setStyleSheet("QFrame { background: #f3f4f6; border-radius: 12px; }")
		led_layout = QVBoxLayout(led_frame)
		led_layout.setContentsMargins(16, 16, 16, 16)
		led_layout.setSpacing(12)

		led_label = QLabel("LED colors")
		led_label.setStyleSheet("font-size: 18px; font-weight: 600;")
		led_layout.addWidget(led_label)

		led_row = QHBoxLayout()
		led_row.setSpacing(10)
		for index, color_hex in enumerate(self.led_colors):
			led_button = LedButton(index, color_hex)
			led_button.color_changed.connect(self.on_led_color_changed)
			led_row.addWidget(led_button)
		led_layout.addLayout(led_row)
		root_layout.addWidget(led_frame)

		controls_frame = QFrame()
		controls_frame.setStyleSheet("QFrame { background: #eef6ff; border-radius: 12px; }")
		controls_layout = QGridLayout(controls_frame)
		controls_layout.setContentsMargins(16, 16, 16, 16)
		controls_layout.setHorizontalSpacing(14)
		controls_layout.setVerticalSpacing(12)

		controls_layout.addWidget(QLabel("Animation"), 0, 0)
		self.animation_combo = QComboBox()
		self.animation_combo.addItems(ANIMATIONS)
		self.animation_combo.currentTextChanged.connect(self.send_current_state)
		controls_layout.addWidget(self.animation_combo, 0, 1)

		controls_layout.addWidget(QLabel("Animation switch key"), 1, 0)
		self.key_button = QPushButton("Choose key")
		self.key_button.clicked.connect(self.enable_key_capture)
		controls_layout.addWidget(self.key_button, 1, 1)

		self.key_label = QLabel("Selected key: None")
		controls_layout.addWidget(self.key_label, 2, 1)
		root_layout.addWidget(controls_frame)

		log_label = QLabel("BLE terminal")
		log_label.setStyleSheet("font-size: 18px; font-weight: 600;")
		root_layout.addWidget(log_label)

		self.log_output = QPlainTextEdit()
		self.log_output.setReadOnly(True)
		root_layout.addWidget(self.log_output)

		self.append_log("Ready. Click 'Start BLE communication' to scan for the Arduino.")

	def start_ble_communication(self) -> None:
		self.append_log("Starting BLE communication...")
		self.ble_controller.connect_to_device()

	def on_connection_changed(self, is_connected: bool) -> None:
		self.is_connected = is_connected
		status_text = "connected" if is_connected else "disconnected"
		self.connection_label.setText(f"Status: {status_text}")
		if is_connected:
			self.connect_button.setText("BLE connected")
			self.send_current_state()
		else:
			self.connect_button.setText("Start BLE communication")

	def on_led_color_changed(self, index: int, color_hex: str) -> None:
		self.led_colors[index] = color_hex
		self.send_current_state()

	def enable_key_capture(self) -> None:
		self.capture_key_mode = True
		self.key_button.setText("Press any key...")
		self.append_log("Key capture enabled. Press a keyboard key to bind the animation switch.")
		self.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

	def keyPressEvent(self, event) -> None:
		if self.capture_key_mode:
			self.capture_key_mode = False
			key_text = self._format_key(event)
			self.selected_key = key_text
			self.key_button.setText("Choose key")
			self.key_label.setText(f"Selected key: {self.selected_key}")
			self.append_log(f"Bound animation switch to key: {self.selected_key}")
			self.send_current_state()
			event.accept()
			return

		super().keyPressEvent(event)

	def closeEvent(self, event) -> None:
		self.ble_controller.stop()
		super().closeEvent(event)

	def send_current_state(self) -> None:
		if not self.is_connected:
			return

		payload = {
			"animation": self.animation_combo.currentText(),
			"key_binding": self.selected_key,
			"led_colors": self.led_colors,
		}
		self.ble_controller.send_payload(json.dumps(payload))

	def append_log(self, message: str) -> None:
		self.log_output.appendPlainText(message)

	@staticmethod
	def _format_key(event) -> str:
		try:
			key_text = QKeySequence(event.keyCombination()).toString()
		except Exception:
			key_text = QKeySequence(event.key()).toString()

		if key_text:
			return key_text

		if event.text():
			return event.text().upper()

		return "Unknown"


def main() -> int:
	application = QApplication(sys.argv)
	window = LedControllerWindow()
	window.show()
	return application.exec()


if __name__ == "__main__":
	raise SystemExit(main())
