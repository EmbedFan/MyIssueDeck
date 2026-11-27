MyIssueDeck installer
=====================

Install or update MyIssueDeck on this Windows computer. Python 3.11 or newer must be
installed (python.org). No internet connection is needed when this is the full installer.

Install:

    install.cmd

Without --target this is a NEW installation in C:\Utility\MyIssueDeck_<version> (one folder per
version, for example C:\Utility\MyIssueDeck_0.10.1), so it never touches an installation that
already exists. To UPDATE an installation, give its folder:

    install.cmd --target C:\Utility\MyIssueDeck_0.10.0

Useful options:

    install.cmd --check                  show what would be done, change nothing
    install.cmd --target FOLDER          install into FOLDER, or update the installation in it
    install.cmd --port 8770              another port (the default 8765 must be free)
    install.cmd --start                  leave the server running at the end
    install.cmd --repair                 reinstall the same version
    install.cmd --silent                 no questions
    install.cmd --online                 download the libraries instead of using the
                                         ones in this installer (also for a Python that
                                         is not 3.11, 3.12 or 3.13)
    install.cmd --import-data FILE.zip   new installation only: import a project snapshot,
                                         or a data folder of another installation

What an update does: it stops only the server of that folder, makes a backup of your data
under backups\, builds the new software next to the old one, applies the database
migrations and starts the server again. Your database, server.toml, settings, projects and
tokens are never replaced. If any step fails the old version is put back. Start and stop
scripts that the first installer named with the spelling "myissuedesk" are renamed to the
names below (a copy is kept in the backup); change a shortcut that points to an old name.

A new installation writes server.toml with a new administrator token. The token is shown
once at the end of the installation; it is stored in server.toml.

Start and stop the server with start-myissuedeck.vbs and stop-myissuedeck.vbs in the
installation folder. USERGUIDE.md in the installation folder explains how to connect an AI
assistant (Claude, Codex and others). The Help button of the dashboard has a part for Claude
and a part for Codex, each with an example prompt that teaches the assistant how to work with
the tracker.

Check the download: the SHA-256 of the ZIP is in the .sha256 file next to it.
