# Network Mount Monitoring

## Overview

Network Mount Monitoring is a Python-based tool designed to monitor and manage network mounts on a Linux system. The tool uses D-Bus interfaces provided by NetworkManager and systemd to monitor network state changes and systemd journal logs for network mount errors. It aims to prevent system hangs due to network mount issues by automatically handling mount and automount units.

## Features

- **NetworkManager D-Bus Monitoring**: Listens to NetworkManager signals for network device state changes and global network state changes.
- **Systemd Journal Monitoring**: Monitors systemd journal for kernel log messages related to network mount errors.
- **Systemd Unit Control**: Manages systemd mount and automount units, including resetting failed units and restarting them as needed.

## Project Structure

```
network_mount_monitoring_project/
├── network_mount_monitoring/
│   ├── __main__.py
│   ├── __init__.py
│   ├── config.py
│   ├── dbus_monitoring.py
│   ├── journal_monitoring.py
│   └── mount_control.py
└── requirements.txt
```
- `network_mount_monitoring/__main__.py`: The main script to run the network mount monitoring.
- `network_mount_monitoring/__init__.py`: Initializes the package.
- `network_mount_monitoring/config.py`: Configuration file for the project, including the list of network mounts.
- `network_mount_monitoring/dbus_monitoring.py`: Contains the `DbusMonitoring` class for monitoring NetworkManager D-Bus signals.
- `network_mount_monitoring/journal_monitoring.py`: Contains the `JournalctlMonitoring` class for monitoring systemd journal logs.
- `network_mount_monitoring/mount_control.py`: Contains the `MountControl` class for controlling systemd units.
- `requirements.txt`: Python dependencies required for the project.

## Installation

1. **Clone the repository**:
    ```sh
    git clone [ THIS PROJECT URL ]
    cd network_mount_monitoring
    ```

2. **Create a virtual environment and activate it**:
    ```sh
    python3 -m venv .venv
    source .venv/bin/activate
    ```

3. **Install the dependencies**:
    ```sh
    pip install -r requirements.txt
    ```

## Configuration

Edit the `network_mount_monitoring/config.py` file to specify the list of network mounts you want to monitor. For example:

```python
NETWORK_MOUNT_NAMES = ["home-vaarlion-Nas", "home-vaarlion-Media"]
```

Note that this expect that you've already created the `.mount` and `.automount` unit yourself.

## Usage

Run the main script to start monitoring:

```sh
python -m network_mount_monitoring
```

## Logging

The project uses the `logging` module to provide information about its operations. By default, it logs to the console. You can configure the logging settings in the `main.py` file by adjusting the `logging.basicConfig` call.

## Contributing

If you would like to contribute to this project, please fork the repository and submit a pull request. For major changes, please open an issue to discuss what you would like to change.

## License

This project is licensed under the GNU GPLv3 License. See the `LICENSE` file for details.

---
