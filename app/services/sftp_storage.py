import os
import logging
from typing import Optional, Tuple

import paramiko

from app.config import settings

logger = logging.getLogger(__name__)


def _get_sftp_client() -> Tuple[paramiko.SSHClient, paramiko.SFTPClient]:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    connect_kwargs = {
        "hostname": settings.data_server_host,
        "port": settings.data_server_port,
        "username": settings.data_server_user,
    }

    if settings.data_server_ssh_key and os.path.exists(settings.data_server_ssh_key):
        connect_kwargs["key_filename"] = settings.data_server_ssh_key
    elif settings.data_server_password:
        connect_kwargs["password"] = settings.data_server_password
    else:
        raise ValueError("SSH key or password required for data server connection")

    ssh.connect(**connect_kwargs)
    sftp = ssh.open_sftp()
    return ssh, sftp


def _ensure_remote_dir(sftp: paramiko.SFTPClient, path: str):
    dirs = []
    while path and path != "/":
        try:
            sftp.stat(path)
            break
        except FileNotFoundError:
            dirs.append(path)
            path = os.path.dirname(path)
    for d in reversed(dirs):
        sftp.mkdir(d)


def upload_to_data_server(
    local_path: str,
    filename: str,
) -> str:
    remote_full = os.path.join(settings.data_server_path, filename)

    ssh, sftp = _get_sftp_client()
    try:
        sftp.put(local_path, remote_full)
        logger.info(f"Uploaded {local_path} -> {remote_full}")
        return remote_full
    finally:
        sftp.close()
        ssh.close()


def is_data_server_configured() -> bool:
    return bool(settings.data_server_host and settings.data_server_user)
