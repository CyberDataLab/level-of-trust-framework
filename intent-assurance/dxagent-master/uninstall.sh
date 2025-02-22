#!/bin/bash

# uninstall.sh - Script to uninstall the DX Agent and its dependencies

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

# Get the directory of the script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
echo_info "Script directory: $SCRIPT_DIR"

# Ask the user if they created a virtual environment
echo_info "Did you create a virtual environment for the DX Agent? (y/n)"
read -r CREATE_VENV

if [[ "$CREATE_VENV" != "y" && "$CREATE_VENV" != "Y" && "$CREATE_VENV" != "n" && "$CREATE_VENV" != "N" ]]; then
    echo_error "Invalid option. Please select y or n."
    exit 1
fi

# Uninstall system dependencies
echo_info "Uninstalling system dependencies"
apt-get remove -y python3-dev libnl-3-dev libnl-route-3-dev

if [ $? -eq 0 ]; then
    echo_success "System dependencies uninstalled successfully"
else
    echo_error "Failed to uninstall system dependencies"
    exit 1
fi

# Uninstall Python dependencies
if [[ "$CREATE_VENV" == "y" || "$CREATE_VENV" == "Y" ]]; then
    # Remove the virtual environment
    VENV_DIR="$SCRIPT_DIR/venv"
    if [ -d "$VENV_DIR" ]; then
        echo_info "Removing virtual environment"
        rm -rf "$VENV_DIR"
        if [ $? -eq 0 ]; then
            echo_success "Virtual environment removed successfully"
        else
            echo_error "Failed to remove virtual environment"
            exit 1
        fi
    else
        echo_info "Virtual environment not found, skipping removal"
    fi
else
    # Uninstall Python packages globally
    echo_info "Uninstalling Python packages globally"
    pip3 uninstall -y -r "$SCRIPT_DIR/requirements.txt"

    if [ $? -eq 0 ]; then
        echo_success "Python packages uninstalled successfully"
    else
        echo_error "Failed to uninstall Python packages"
        exit 1
    fi
fi

# Remove gNMI certs
echo_info "Do you want to remove the gNMI certificates? (y/n)"
read -r REMOVE_CERTS

if [[ "$REMOVE_CERTS" == "y" || "$REMOVE_CERTS" == "Y" ]]; then
    echo_info "Are you sure you want to remove the gNMI certificates? (y/n)"
    read -r CONFIRM_REMOVE_CERTS
    if [[ "$CONFIRM_REMOVE_CERTS" == "y" || "$CONFIRM_REMOVE_CERTS" == "Y" ]]; then
        echo_info "Removing gNMI certificates"
        
        # Remove all files in the certs directory except gen_certs.sh
        find "$SCRIPT_DIR/certs" -type f ! -name 'gen_certs.sh' -exec rm -f {} +
        
        # Check if the files were removed successfully
        if [ $? -eq 0 ]; then
            echo_success "gNMI certificates removed successfully"
        else
            echo_error "Failed to remove gNMI certificates"
            exit 1
        fi
    else
        echo_info "Skipping removal of gNMI certificates"
    fi
else
    echo_info "Skipping removal of gNMI certificates"
fi

# Cleanup
echo_info "Cleaning up APT cache"
apt-get autoremove -y
apt-get clean

echo_success "DX Agent uninstallation completed successfully"

# End of script
exit 0