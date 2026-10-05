import signal
import sys

from PyQt6.QtCore import QTimer


def main(argv=None):
	argv = sys.argv if argv is None else argv
	if len(argv) > 1 and argv[1] in ("export", "--help", "-h"):
		from .cli import main as cli_main
		return cli_main(argv[1:])
	from dlii_labeler.application import Application
	from dlii_labeler.main_window import MainWindow
	app = Application(argv)

	def handle_sigint(_signal, _frame):
		app.closeAllWindows()

	signal.signal(signal.SIGINT, handle_sigint)
	# Keep Python signal handlers responsive while Qt owns the event loop.
	signal_poll_timer = QTimer(app)
	signal_poll_timer.setInterval(100)
	signal_poll_timer.timeout.connect(lambda: None)
	signal_poll_timer.start()

	if not app.openFolder(argv[1] if len(argv) > 1 else None):
		return 0
	main_window = MainWindow()
	main_window.show()
	return app.exec()

if __name__ == "__main__":
	sys.exit(main(sys.argv))
