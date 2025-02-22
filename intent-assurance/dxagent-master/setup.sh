#!/bin/bash

# setup.sh - Script to install the DX Agent on a Linux machine
# This script will install Python3, pip, and DxAgent dependencies on the machine.

# Function to show info messages
function echo_info() {
    echo -e "\e[96mINFO: $1\e[0m"
}

# Function to show error messages
function echo_error() {
    echo -e "\e[91mERROR: $1\e[0m"
}

# Function to show success messages
function echo_success() {
    echo -e "\e[92mSUCCESS: $1\e[0m"
}

# Check if the script is running as root
if [ "$EUID" -ne 0 ]; then
    echo_error "Please run this script as root or using sudo"
    exit 1
fi

# Identify the user running sudo

if [ -n "$SUDO_USER" ] && [ "$SUDO_USER" != "root" ]; then
    USER_NAME="$SUDO_USER"
    USER_HOME=$(getent passwd "$USER_NAME" | cut -d: -f6)
else
    echo_error "Cannot identify a non-root user. Make sure to run the script with sudo from a non-root user account."
    exit 1
fi

echo_info "User identified: $USER_NAME with home directory: $USER_HOME"

# Ask the user which arquitecture is the machine
echo_info "Which arquitecture is the machine? (1) x86_64 or (2) arm64"
read -r ARQUITECTURE

# Setting up files for the arquitecture

if [[ "$ARQUITECTURE" == "1" ]]; then
    echo_info "Setting up files for x86_64 arquitecture"
    mv aux/bm_input_x86.py agent/input/bm_input.py
elif [[ "$ARQUITECTURE" == "2" ]]; then
    echo_info "Setting up files for arm64 arquitecture"
    mv aux/bm_input_arm.py agent/input/bm_input.py
else
    echo_error "Invalid arquitecture. Please select 1 or 2."
    exit 1
fi

# Ask the user if they want to crear a virtual environment
echo_info "Do you want to create a virtual environment for the DX Agent? (y/n)"
read -r CREATE_VENV

if [[ "$CREATE_VENV" != "y" || "$CREATE_VENV" != "Y" || "$CREATE_VENV" != "n" || "$CREATE_VENV" != "N" ]]; then
    echo_info "Invalid option. Please select y or n."
    exit 1
fi

# Get the directory of the script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
echo_info "Script directory: $SCRIPT_DIR"

# Update the package list
echo_info "Updating package list"
apt-get update -y


# Function to check if a command exists
function command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# 1. Install Python3
echo_info "Installing Python3"
apt-get install -y python3 python3-pip python3-venv
if command_exists python3; then
    echo_success "Python3 installed successfully"
else
    echo_error "Failed to install Python3"
    exit 1
fi

# 2. Install pip
if command_exists pip3; then
    echo_success "pip is already installed"
else
    echo_info "Installing pip"
    apt-get install -y python3-pip
    if command_exists pip3; then
        echo_success "pip installed successfully"
    else
        echo_error "Failed to install pip"
        exit 1
    fi
fi

# 3. Create a virtual environment


if [[ "$CREATE_VENV" == "y" || "$CREATE_VENV" == "Y" ]]; then
    # Create a virtual environment
    echo_info "Creating a virtual environment"
    VENV_DIR="$SCRIPT_DIR/venv"
    sudo -u "$USER_NAME" python3 -m venv "$VENV_DIR"

    if [ -d "$VENV_DIR" ]; then
        echo_success "Virtual environment created successfully"
    else
        echo_error "Failed to create a virtual environment"
        exit 1
    fi

    # 4. Check if pip is installed in the virtual environment
    if ! sudo -u "$USER_NAME" "$VENV_DIR/bin/python" -m pip --version >/dev/null 2>&1; then
        echo_info "Pip not found in virtual environment. Installing pip..."
        sudo -u "$USER_NAME" "$VENV_DIR/bin/python" -m ensurepip --upgrade
        if sudo -u "$USER_NAME" "$VENV_DIR/bin/python" -m pip --version >/dev/null 2>&1; then
            echo_success "Pip installed in the virtual environment."
        else
            echo_error "Failed to install pip in the virtual environment."
            exit 1
        fi
    else
        echo_info "Pip is already installed in the virtual environment."
    fi

    echo_info "Updating pip in the virtual environment..."
    sudo -u "$USER_NAME" "$VENV_DIR/bin/python" -m pip install --upgrade pip

    # 5. Install the dependencies in the virtual environment
    echo_info "Installing the dependencies in the virtual environment"
    apt install -y python3-dev libnl-3-dev libnl-route-3-dev
    sudo -u "$USER_NAME" "$VENV_DIR/bin/python" -m pip install -r "$SCRIPT_DIR/requirements.txt"

    if [ $? -eq 0 ]; then
        echo_success "Dependencies installed successfully in the virtual environment"
    else
        echo_error "Failed to install dependencies in the virtual environment"
        exit 1
    fi

    # 6. Cleanup
    echo_info "Cleaning up APT cache"
    apt-get clean

    echo_success "DX Agent setup completed successfully"

    echo
    echo

    echo_info "To activate the virtual environment, run: source $VENV_DIR/bin/activate"
    echo_info "To deactivate the virtual environment, run: deactivate"

    echo
    echo

    echo_info "To start the DX Agent, run: sudo $VENV_DIR/bin/python dxagent (start|stop|status)"

else
    # Install dependencies globally
    echo_info "Installing the dependencies globally"
    apt install -y python3-dev libnl-3-dev libnl-route-3-dev
    pip3 install -r "$SCRIPT_DIR/requirements.txt"

    if [ $? -eq 0 ]; then
        echo_success "Dependencies installed successfully globally"
    else
        echo_error "Failed to install dependencies globally"
        exit 1
    fi

    # Cleanup
    echo_info "Cleaning up APT cache"
    apt-get clean

    echo_success "DX Agent setup completed successfully"

    echo
    echo

    echo_info "To start the DX Agent, run: sudo python3 dxagent (start|stop|status)"
fi

# 7. Set certificates for gNMI exporter

echo_info "Are you going to use gNMI exporter? (y/n)"
read -r USE_GNMI

if [[ "$USE_GNMI" == "y" || "$USE_GNMI" == "Y" ]]; then
    echo_info "Which is the server hostname for the gNMI exporter?"
    read -r SERVER_HOSTNAME
    echo_info "Which is the server IP for the gNMI exporter?"
    read -r SERVER_IP
    cd certs/
    ./gen_certs.sh "$SERVER_HOSTNAME" "$SERVER_IP"
    cd ..
    if [ $? -eq 0 ]; then
        echo_success "Certificates for gNMI exporter generated successfully"
    else
        echo_error "Failed to generate certificates for gNMI exporter"
        exit 1
    fi
else
    echo_info "Skipping setting up certificates for gNMI exporter"
fi

# End of script
exit 0
