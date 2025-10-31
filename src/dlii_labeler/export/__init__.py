from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING
from PyQt6.QtWidgets import QWidget

if TYPE_CHECKING:
	from ..application import Application

class Exporter:

	def __init__(self):
		pass

	def app(self) -> "Application":
		from ..application import Application
		return Application.instance()

	def export(self, options: Any) -> None:
		raise NotImplementedError

	def show(self, parent: Optional[QWidget] = None) -> None:
		raise NotImplementedError
