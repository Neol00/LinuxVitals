#!/bin/bash

# Function to find the correct Python executable
find_python_command() {
    # List of possible Python commands to check
    python_candidates=("python3" "python" "python3.11" "python3.10" "python3.9" "python3.8")

    for cmd in "${python_candidates[@]}"; do
        if command -v "$cmd" >/dev/null 2>&1; then
            # Check if it's Python 3
            version_output=$("$cmd" --version 2>&1)
            if echo "$version_output" | grep -q "Python 3"; then
                echo "$cmd"
                return 0
            fi
        fi
    done

    echo "python3"  # Fallback to python3
    return 1
}

# Get the absolute path of the directory where this install.sh script is located
# This is the LinuxVitals directory, regardless of where it's installed
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
linuxvitals_path="$SCRIPT_DIR"

# Verify this is actually the LinuxVitals directory by checking for key files
if [ ! -f "$linuxvitals_path/launch.py" ] || [ ! -d "$linuxvitals_path/icon" ]; then
    echo "Error: This doesn't appear to be the LinuxVitals directory."
    echo "Expected to find launch.py and icon/ directory in: $linuxvitals_path"
    exit 1
fi

echo "LinuxVitals directory found at: $linuxvitals_path"

# Detect the correct Python command
python_cmd=$(find_python_command)
python_full_path=$(which "$python_cmd" 2>/dev/null)

if [ -z "$python_full_path" ]; then
    echo "Warning: Python 3 not found. Using 'python3' as fallback."
    python_full_path="python3"
else
    echo "Found Python at: $python_full_path"
fi

# Create the applications directory if it doesn't exist
mkdir -p $HOME/.local/share/applications

# Create the .desktop file
cat << EOF > $HOME/.local/share/applications/org.LinuxVitals.desktop
[Desktop Entry]
Version=1.0
Type=Application
Name=LinuxVitals
Comment=Monitor and control your CPU
Exec=$python_full_path $linuxvitals_path/launch.py
Icon=$linuxvitals_path/icon/LinuxVitals-Icon.png
Terminal=false
Categories=Utility;Application;
StartupWMClass=org.LinuxVitals
EOF

# Make the .desktop file executable
chmod +x $HOME/.local/share/applications/org.LinuxVitals.desktop

# Update desktop database to refresh icon cache
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database $HOME/.local/share/applications 2>/dev/null
fi

echo ""
echo "✓ LinuxVitals installation completed successfully!"
echo ""
echo "Installation details:"
echo "  • Desktop file: $HOME/.local/share/applications/org.LinuxVitals.desktop"
echo "  • Python executable: $python_full_path"
echo "  • LinuxVitals path: $linuxvitals_path"
echo "  • Icon path: $linuxvitals_path/icon/LinuxVitals-Icon.png"
echo ""
echo "You can now launch LinuxVitals from your application menu or by running:"
echo "  python3 $linuxvitals_path/launch.py"
echo ""