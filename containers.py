import docker
import os
import tarfile
from docker.models.containers import Container

client = docker.from_env()


def copy_to(src, dst):
    name, dst = dst.split(":")
    container = client.containers.get(name)

    os.chdir(os.path.dirname(src))
    srcname = os.path.basename(src)
    tar = tarfile.open(src + ".tar", mode="w")
    try:
        tar.add(srcname)
    finally:
        tar.close()

    data: bytes = open(src + ".tar", "rb").read()
    container.put_archive(os.path.dirname(dst), data)


async def init_container(name: str) -> Container:
    container: Container = client.containers.run(
        "8e39204f13a6",  # python 3.13.7-slim
        command="sleep 3600",
        name=name,
        detach=True,
        tty=True,
    )

    return container


def upload_file(path: str | dict[str, str], container: Container):
    if isinstance(path, dict):
        for p in path.keys():
            copy_to(p, f"{container.name}:/{path[p]}")
    copy_to(path, f"{container.name}:/main.py")


def run_script(filename: str, container: Container) -> str:
    out = container.exec_run(f"python {filename}", tty=True)

    return out.output.decode()


def run_command(command: str, container: Container) -> str:
    out = container.exec_run(command, tty=True)

    return out.output.decode()


def download_files(container: Container, files: list[str]) -> list[bytes]:
    tars = []
    for p in files:
        stream, _ = container.get_archive(p)
        chunks = []
        for chunk in stream:
            chunks.append(chunk)
        tars.append(b"".join(chunks))
    return tars


def get_file_type(filename: str) -> str:
    return filename.split(".")[-1]
