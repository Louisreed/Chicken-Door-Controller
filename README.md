# Chicken Door Controller

## Overview

The Chicken Door Controller is a Raspberry Pi-based system designed to automate the opening and closing of a chicken coop door. The door opens at 6:00 AM and closes at 8:00 PM every day. Additionally, the system provides a simple HTTP API for remote manual control of the door.

## Requirements

- Raspberry Pi with GPIO support
- Python 3.x
- Flask Python package

## Installation

1. Make sure Python 3.x is installed on your Raspberry Pi. You can install it using:

    ```bash
    sudo apt-get install python3
    ```

2. Install Flask. Since the Raspberry Pi doesn't have internet access, download the Flask package on another machine and transfer it to the Pi.

3. Place the `chickenDoorController.py` script in your desired directory.

4. (Optional) Set up the script to run as a systemd service for automatic execution on boot.

5. (Optional) Start the Script manually

```bash
sudo python3 /home/user/chickenDoorController.py
```

## Copy Script to Raspberry Pi

To copy the script to your Raspberry Pi, you can use the `scp` (Secure Copy Protocol) command. Open a terminal on your computer and run:

```bash
scp chickenDoorController.py [user]@[Your_Raspberry_Pi_IP_Address]:
```

## Usage

### Automatic Scheduling

By default, the door will open at 6:00 AM and close at 8:00 PM every day.

### Manual Control via HTTP API

To manually control the door, navigate to the following URLs:

- Open Door: `http://[Your_Raspberry_Pi_IP_Address]:5000/open_door`
- Close Door: `http://[Your_Raspberry_Pi_IP_Address]:5000/close_door`

Replace `[Your_Raspberry_Pi_IP_Address]` with the actual IP address of your Raspberry Pi.

**Note**: Running the Flask app with `host='0.0.0.0'` makes the API accessible from any IP address. This could be a security risk if your Raspberry Pi is exposed to the internet. Use this setting carefully and consider implementing additional security measures, such as API authentication.

## Contributing

Feel free to contribute to this project by submitting pull requests or issues.

## License

This project is open-source and available under the MIT License.
