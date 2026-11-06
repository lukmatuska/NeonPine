#!/bin/sh
# Runs the NeonPine Companion from this checkout like an installed app: a menu entry with an icon, and
# (with --udev) the udev rule that lets you use the tree without root.
#   packaging/install_linux.sh [--udev]
#   packaging/install_linux.sh --uninstall
set -e
HERE=$(cd "$(dirname "$0")/.." && pwd)
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ICONS="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/256x256/apps"

if [ "$1" = "--uninstall" ]; then
	rm -f "$APPS/neonpine-companion.desktop" "$ICONS/neonpine-companion.png"
	echo "removed the menu entry"
	exit 0
fi

python3 -c "import PySide6" 2>/dev/null || {
	echo "PySide6 is missing: install it (Arch: pacman -S pyside6, Debian/Ubuntu: apt install python3-pyside6.qtwidgets python3-pyside6.qtmultimedia, or pip install PySide6)"
	exit 1
}
mkdir -p "$APPS" "$ICONS"
python3 "$HERE/packaging/make_icons.py" "$HERE/build" >/dev/null
cp "$HERE/build/neonpine-companion.png" "$ICONS/"
cat > "$APPS/neonpine-companion.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=NeonPine Companion
Comment=Control, animate and update your NeonPine tree
Exec=python3 "$HERE/neonpine-companion.py"
Icon=neonpine-companion
Terminal=false
Categories=Utility;
StartupWMClass=neonpine-companion
DESKTOP
echo "menu entry: $APPS/neonpine-companion.desktop"

if [ "$1" = "--udev" ]; then
	sudo cp "$HERE/../firmware/tools/99-neonpine.rules" /etc/udev/rules.d/
	sudo udevadm control --reload
	sudo udevadm trigger
	echo "udev rule installed - replug the tree (your user must be in the 'plugdev' group: sudo usermod -aG plugdev \$USER)"
fi
