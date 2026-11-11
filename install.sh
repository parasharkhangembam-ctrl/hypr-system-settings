#!/usr/bin/env bash
# install.sh  ->  install System Settings for your user (no sudo).
#   ./install.sh               install
#   ./install.sh --uninstall   remove it
set -u
cd "$(dirname "$(readlink -f "$0")")"
BIN="$HOME/.local/bin/system-settings"
APP="${XDG_DATA_HOME:-$HOME/.local/share}/applications/system-settings.desktop"
if [ "${1:-}" = --uninstall ]; then rm -f "$BIN" "$APP"; echo "  ✓ removed"; exit 0; fi

python3 -c 'import gi; gi.require_version("Gtk", "3.0"); from gi.repository import Gtk' 2>/dev/null \
  || { echo "  ✗ needs PyGObject + GTK 3 (Fedora: sudo dnf install python3-gobject gtk3)"; exit 1; }
for c in nmcli bluetoothctl wpctl pactl; do
  command -v "$c" >/dev/null || echo "  • '$c' not found: its pane will be empty"
done
mkdir -p "${BIN%/*}" "${APP%/*}"
install -m 755 system-settings.py "$BIN"
cat > "$APP" <<DESK
[Desktop Entry]
Type=Application
Name=System Settings
Comment=Wi-Fi, Bluetooth, Sound, Displays and Battery
Exec=$BIN
Icon=preferences-system
Categories=Settings;
DESK
echo "  ✓ installed: run 'system-settings' or open it from your launcher"
echo "  Optional keybind (hyprland.lua):  hl.bind(\"SUPER + comma\", hl.dsp.exec_cmd(\"$BIN\"))"
