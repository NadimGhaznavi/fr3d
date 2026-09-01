# Fr3d

Another AI Project...

## Installation

Fr3d requires MariaDB, llama.cpp, and the configured Qwen model to exist before installation. Run the installer as root from the source checkout.

The installer recreates the fr3d MariaDB database and database account, writes generated credentials to /etc/fr3d/database.env, installs the application under /opt/fr3d, and installs the systemd service.

    sudo ./scripts/install.py

Use the upgrade script to preserve the existing database and credentials while updating application code and dependencies.

    sudo ./scripts/upgrade.sh

The uninstall script removes the application, service account, credentials, and MariaDB database.

    sudo ./scripts/uninstall.py
