import sys

from .application import Application
from .main_window import MainWindow

def main(argv):
	app = Application(argv)
	if not app.openFolder(argv[1] if len(argv) > 1 else None):
		return 0
	main_window = MainWindow()
	main_window.show()
	return app.exec()

if __name__ == "__main__":
	sys.exit(main(sys.argv))
