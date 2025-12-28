from mcp.server.fastmcp import FastMCP, Image, Context
from mcp.types import ImageContent
from mcp.server.session import ServerSession

from docker.models.containers import Container

import graph
import containers
import search
import image

# import requests

import os
import stat
import tempfile
import uuid
import io
import matplotlib
import tarfile
from matplotlib._pylab_helpers import Gcf

import pandas as pd

from typing import Optional, Literal, Annotated

FILES_DIR = os.path.join(tempfile.gettempdir(), "mcp_files")
os.makedirs(FILES_DIR, exist_ok=True)
PATH = os.path.abspath(FILES_DIR)

matplotlib.use("Agg")


def _save_file_to_disk(
    filename: str, data: bytes | str, method="b", use_uuid=True
) -> str:
    """
    Save `data` to FILES_DIR using a sanitized filename.
    - prevents directory traversal by using only the basename
    - if a file with the same name exists, appends a short uuid
    - sets restrictive owner read/write permissions when possible
    Returns the absolute path to the saved file.
    """

    base = os.path.basename(filename)
    if not base:
        base = uuid.uuid4().hex

    dest = os.path.join(FILES_DIR, base)

    if os.path.exists(dest):
        name, ext = os.path.splitext(base)
        if use_uuid:
            dest = os.path.join(FILES_DIR, f"{name}-{uuid.uuid4().hex}{ext}")
        else:
            os.path.join(FILES_DIR, f"{name}")

    tmp_path = dest + f".tmp-{uuid.uuid4().hex}"
    with open(tmp_path, "w" + method, encoding="utf-8" if method != "b" else None) as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())

    os.replace(tmp_path, dest)

    try:
        os.chmod(dest, stat.S_IRUSR | stat.S_IWUSR)
    except Exception:
        pass

    return "file:///" + os.path.abspath(dest)


def _save_fig_to_bytes(fig, fmt: str = "png") -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format=fmt, bbox_inches="tight")
    buf.seek(0)
    return buf.read()


def _make_imagecontent_from_bytes(data: bytes, fmt: str = "png") -> ImageContent:
    mcp_image = Image(data=data, format=fmt)
    return mcp_image.to_image_content()


def _fig_to_compatible_output(fig) -> ImageContent:
    """
    Returns:
      - ImageContent (existing behavior) for PNG/JPEG figures
    """

    data = _save_fig_to_bytes(fig, fmt="png")
    _save_file_to_disk(f"{uuid.uuid4().hex}.png", data, "b")
    return _make_imagecontent_from_bytes(data, fmt="png")


mcp = FastMCP(
    "Demo",
    instructions="""
Use Knowledge Graph tools with natural language. E.g.:

```
"The sun provides energy to plants through photosynthesis",
"Rabbits eat grass and other plants for nutrition",
"Foxes hunt rabbits as their primary food source",
"Grass grows in the meadow environment",
"Oak trees provide shelter for various animals",
"Rabbits live in the meadow alongside other creatures",
"Foxes also inhabit the meadow ecosystem"
```

For Querying use keywords previously used, E.g.: `Foxes` or `plants`
------------------------------------------------
Stop virtual environments after use.
------------------------------------------------
*Always* provide citations with web searches.
E.g.:
```
This domain is for use in documentation examples without needing permission. Avoid use in operations.[^1]

[^1]: https://www.example.com/, Main Paragraph
```

OR use links:
```
This domain is for use in documentation examples without needing permission. Avoid use in operations.

Source: [example.com](https://www.example.com/)
```

The best way would be to use *both*:
```
This domain is for use in documentation examples without needing permission. Avoid use in operations.[^1]

Sources: 
[^1]: [example.com](https://www.example.com/), Main Paragraph
```

If none works, fall back to just naming sources and adressing them
------------------------------------------------

When retrieving files and recieving a `file_link` **ALWAYS** explicitly repeating it to the user by providing it as a link. EVEN IF IT WAS IN A TOOL RESPONSE!
E.g.:
```
Here's your PDF report: [report.pdf](file:///path/provided/by/file_link)
```
              """,
)

graphs: dict[str, tuple[ImageContent, pd.DataFrame, list[str]]] = {}
container: Container
files: list[str] = []


@mcp.tool()
async def knowledge_graph(
    name: str, graph_data: list[str], ctx: Context[ServerSession, None]
) -> tuple[ImageContent, str, dict]:
    """Create a Knowledge Graph with the name `name`"""
    data = await graph.knowledge_graph(name, graph_data, ctx)

    active_managers = Gcf.get_all_fig_managers()
    fig = active_managers[-1].canvas.figure
    img = _fig_to_compatible_output(fig)
    graphs[name] = img, data, graph_data

    return img, f"Created Graph `{name}` with data: ", data.to_dict()["sentence"]


@mcp.tool()
async def get_graph(name: str) -> tuple[ImageContent, dict]:
    """Read a Knowleadge graph by name"""
    return graphs[name][0], graphs[name][1].to_dict()["sentence"]


@mcp.tool()
async def update_graph(
    ctx: Context[ServerSession, None],
    name: str,
    new_data: list[str],
    removable_data: list[str] = [],
) -> tuple[ImageContent, str, dict]:
    """Update the Knowleadge graph `name` by adding `new_data` and removing `removable_data`"""

    for x in removable_data:
        if x in graphs[name][2]:
            graphs[name][2].remove(x)

    import matplotlib.pyplot as plt

    plt.close("all")
    merged_input = [*graphs[name][2], *new_data]

    data = await graph.knowledge_graph(name, merged_input, ctx)

    active_managers = Gcf.get_all_fig_managers()

    fig = active_managers[-1].canvas.figure
    img = _fig_to_compatible_output(fig)

    graphs[name] = img, data, merged_input
    return img, f"Updated Graph `{name}`. Data: ", data.to_dict()["sentence"]


@mcp.tool()
async def querry_graph(name: str, querry: str, ctx: Context[ServerSession, None]):
    results = []
    for i in graphs[name][2]:
        if querry in i:
            results.append(i)
    return results


@mcp.tool()
async def venv(name: str):
    """Create a virtual environment with python preinstalled"""
    global container
    container = await containers.init_container(name)
    return "Done!"


@mcp.tool()
async def run_py(code: str, name: str = "main.py"):
    """Run Python code in a environment (create with the venv tool)"""
    path = _save_file_to_disk(name, code, "", False).removeprefix("file:///")
    containers.upload_file(path, container)
    return containers.run_script(name, container)


@mcp.tool()
async def run_cmd(cmd: str):
    """Run the command `cmd` in a environment (create with the venv tool)"""
    return containers.run_command(cmd, container)


@mcp.tool()
async def pip_install(packages: Annotated[str, "Packages separates by a space (` `)"]):
    """Install python packages using pip"""
    return containers.run_command(
        f"pip install {packages} --progress-bar off --no-color", container
    )


@mcp.tool()
async def retrieve_files(
    files: list[str],
) -> list[list[str | bytes | ImageContent]]:
    final: list[list[str | bytes | ImageContent]] = []
    tars: list[bytes] = containers.download_files(container, files)
    for tar_bytes in tars:
        with io.BytesIO(tar_bytes) as bio, tarfile.open(fileobj=bio) as tf:
            for member in tf.getmembers():
                f: Optional[io.BytesIO] = tf.extractfile(member)
                if f:
                    match member.name.split(".")[-1].lower():
                        case "pdf":
                            link = _save_file_to_disk(member.name, f.read())
                            final.append(
                                [
                                    f"Name: `{member.name}`",
                                    "File type: `PDF`",
                                    f"file_link: `{link}`",
                                ]
                            )
                        case "png" | "jpg" | "jpeg" | "gif" | "webp" | "avif":
                            image_ = _make_imagecontent_from_bytes(f.read())
                            link = _save_file_to_disk(member.name, f.read())
                            final.append(
                                [
                                    f"Name: `{member.name}`",
                                    "File type: `Image`",
                                    image_,
                                    f"file_link: `{link}`",
                                ]
                            )
                        case "doc" | "docx":
                            link = _save_file_to_disk(member.name, f.read())
                            final.append(
                                [
                                    f"Name: `{member.name}`",
                                    "File type: `Word Document`",
                                    f"file_link: `{link}`",
                                ]
                            )
                        case _:
                            link = _save_file_to_disk(member.name, f.read())
                            final.append(
                                [
                                    f"Name: `{member.name}`",
                                    f"File type: `{member.name.split(".")[-1].lower()}` (Unknown)",
                                    f"contents: `{f.read()}`",
                                    f"file_link: `{link}`",
                                ]
                            )

    return final


@mcp.tool()
async def stop_venv():
    """Stop a virtual environment. Always use after finishing."""
    container.stop()
    return "Done!"


@mcp.tool()
async def restart_venv():
    """Restart a virtual environment after stoping it"""
    container.start()
    return "Done!"


@mcp.tool()
async def web_search(
    query: str,
    topic: Optional[Literal["general", "news", "finance"]] = None,
    time_range: Optional[Literal["day", "week", "month", "year"]] = None,
    start_date: Optional[search.Date] = None,
    end_date: Optional[search.Date] = None,
    max_results: Optional[search.ZeroToTwenty] = None,
    include_images: bool = False,
    include_image_descriptions: bool = False,
    include_domains: Optional[list[str]] = None,
    exclude_domains: Optional[list[str]] = None,
):
    """Search the web on a topic. Use citations as explained in the instructions."""
    s = search.search(
        query,
        topic,
        time_range,
        start_date,
        end_date,
        max_results,
        include_images,
        include_image_descriptions,
        include_domains,
        exclude_domains,
    )
    return s


@mcp.tool()
async def visit(url: str) -> list[dict[str, str | list]]:
    """Visit a url. Optainable using `web_search`. Use citations as explained in the instructions."""
    return search.visit(url)


@mcp.tool()
async def split_image(path: str, num_squares: tuple[int, int] = (10, 8)):
    image.split_image(path, num_squares)

    active_managers = Gcf.get_all_fig_managers()
    fig = active_managers[-1].canvas.figure
    img = _fig_to_compatible_output(fig)

    return img


@mcp.tool()
async def ocr(path: str):
    out = image.ocr(path)

    active_managers = Gcf.get_all_fig_managers()
    fig = active_managers[-1].canvas.figure
    img = _fig_to_compatible_output(fig)

    return img, out



if __name__ == "__main__":
    mcp.run(transport="stdio")
