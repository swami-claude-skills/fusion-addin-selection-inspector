#!/bin/bash
# Double-click installer for macOS. Copies this add-in into Fusion's AddIns folder.
set -euo pipefail

ADDIN_NAME="SelectionInspector"

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST_ROOT="$HOME/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns"
DEST_DIR="$DEST_ROOT/$ADDIN_NAME"

echo "Installing $ADDIN_NAME ..."
echo "  from: $SRC_DIR"
echo "  to:   $DEST_DIR"

if [ ! -d "$DEST_ROOT" ]; then
    echo ""
    echo "AddIns folder not found. Is Fusion installed for this user?"
    echo "Expected: $DEST_ROOT"
    read -r -p "Press Return to close."
    exit 1
fi

if [ "$SRC_DIR" = "$DEST_DIR" ]; then
    echo ""
    echo "This copy is already in Fusion's AddIns folder; nothing to do."
    read -r -p "Press Return to close."
    exit 0
fi

rm -rf "$DEST_DIR"
mkdir -p "$DEST_DIR"
cp -R "$SRC_DIR"/. "$DEST_DIR"/
rm -f "$DEST_DIR"/*.command "$DEST_DIR"/*.ps1 "$DEST_DIR"/*.cmd "$DEST_DIR/READ ME FIRST.txt" "$DEST_DIR"/README.txt
find "$DEST_DIR" -name '.DS_Store' -type f -delete 2>/dev/null || true
find "$DEST_DIR" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true

echo ""
echo "Done. In Fusion: Utilities > Add-Ins > Scripts and Add-Ins (Shift+S),"
echo "select \"$ADDIN_NAME\" under Add-Ins, and turn on Run and Run on Startup."
echo ""
echo "The Selection Inspector button is in the INSPECT panel of every tab."
echo "The version shown in Scripts and Add-Ins only catches up after Fusion restarts;"
echo "the palette title shows the version actually running."
echo "Your keyboard shortcut and settings are kept across reinstalls."
read -r -p "Press Return to close."
