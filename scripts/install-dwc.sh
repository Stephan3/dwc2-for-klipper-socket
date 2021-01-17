#!/bin/bash

#
# Install klipper first and make sure the service is running fine before running this!
#

DWC_KLIPPER_FOLDER="dwc2-for-klipper-socket"

check_installed()
{
    if ! builtin type -p "$1" &>/dev/null; then
        echo "can't find '$1', please install it first!"
        exit -1
    fi
}

install_dwc()
{
    report_status "Checking dependencies"
    check_installed git
    check_installed wget
    check_installed pip3
    check_installed unzip

    DWC_DOWNLOAD_URL="https://github.com/Duet3D/DuetWebControl/releases/download/3.1.1/DuetWebControl-SD.zip"
    DWC_ZIP_NAME="DuetWebControl-SD.zip"
    DWC_KLIPPER_REPO="https://github.com/Stephan3/dwc2-for-klipper-socket"
    DWC_DIR="sdcard/web"

    report_status "Installing python libraries"
    pip3 install tornado

    pushd "$HOME"

    report_status "getting dwc2-for-klipper-socket"
    if [ ! -d "$DWC_KLIPPER_FOLDER" ] ; then
        git clone $DWC_KLIPPER_REPO --depth 1
    fi

    report_status "getting dwc"
    mkdir -p "$DWC_DIR"
    cd "$DWC_DIR"

    wget $DWC_DOWNLOAD_URL
    if [ $? -eq 0 ] ; then
        unzip $DWC_ZIP_NAME
        for f_ in $(find . | grep '.gz');do gunzip ${f_};done
        rm $DWC_ZIP_NAME
    fi

    popd
}

fix_klipper_service()
{
    report_status "Patching existing klipper.service file"

    KLIPPER_SERVICE="/etc/systemd/system/klipper.service"

    if [ ! -e "$KLIPPER_SERVICE" ] ; then
        echo "looks like klipper service isn't installed, please install it first"
        exit 1
    fi

    EXTRA_ARG="-a /tmp/klippy_uds"
     
    if grep -q $EXTRA_ARG $KLIPPER_SERVICE ; then
        return
    fi

    # add extra arg to klipper service file
    sudo sed -i '/ExecStart/s/$/ -a \/tmp\/klippy_uds/' $KLIPPER_SERVICE
}

install_dwc_service()
{
    PYTHON_DIR="/usr/bin/python3"
    DWC_SERVICE="/etc/systemd/system/dwc.service"
    ENTRY_POINT="web_dwc2.py"

    if [ -e "$DWC_SERVICE" ] ; then
        echo "DWC service is already installed"
        return
    fi

    DIR=${PWD##*/}

    if [ "$DIR" = "$DWC_KLIPPER_FOLDER" ] ; then
        WORKING_DIR=$(pwd)
    elif [ "$DIR" = "scripts" ] ; then
        WORKING_DIR=$(cd .. && pwd)
    else
        echo "please run this script from the $DWC_KLIPPER_FOLDER directory!"
        exit 0
    fi

    # Create systemd service file
    report_status "Installing DWC service..."
    sudo /bin/sh -c "cat > $DWC_SERVICE" << EOF
# Systemd service file for dwc2 web interface
[Unit]
Description=DWC Interface
After=klipper.service

[Service]
ExecStart= $PYTHON_DIR $WORKING_DIR/$ENTRY_POINT
WorkingDirectory=$WORKING_DIR

[Install]
WantedBy=multi-user.target
EOF
}

start_services()
{
    report_status "Launching services..."
    sudo systemctl daemon-reload

    sudo systemctl enable klipper
    sudo systemctl restart klipper

    sudo systemctl enable dwc
    sudo systemctl start dwc
}

# Helper functions
report_status()
{
    echo -e "###### $1"
}

verify_ready()
{
    if [ "$EUID" -eq 0 ]; then
        echo "This script must not run as root"
        exit -1
    fi
}

# Force script to exit if an error occurs
set -e

# Run installation steps defined above
verify_ready
install_dwc
install_dwc_service
fix_klipper_service
start_services
