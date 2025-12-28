import matplotlib.pyplot as plt
import matplotlib.ticker as plticker
from PIL import Image, ImageDraw
from typing import IO
import easyocr


def split_image(path_or_bytes: str | IO[bytes], num_squares: tuple[int, int] = (10, 8)):
    image = Image.open(path_or_bytes)
    dpi = 300

    nx, ny = num_squares

    fig = plt.figure(
        figsize=(float(image.size[0]) / dpi, float(image.size[1]) / dpi),
        dpi=dpi,
    )
    ax = fig.add_subplot(111)

    fig.subplots_adjust(left=0, right=1, bottom=0, top=1)

    width, height = image.size
    xInterval = width / nx
    yInterval = height / ny

    ax.xaxis.set_major_locator(plticker.MultipleLocator(base=xInterval))
    ax.yaxis.set_major_locator(plticker.MultipleLocator(base=yInterval))

    ax.grid(which="major", axis="both", linestyle="-")

    ax.imshow(image)

    for j in range(ny):
        y = yInterval / 2 + j * yInterval
        for i in range(nx):
            x = xInterval / 2 + i * xInterval
            ax.text(
                x,
                y,
                "{:d}".format(i + j * nx),
                color="w",
                ha="center",
                va="center",
                fontsize=5,
            )

    # Save the figure
    fig.savefig("OIP2.webp", dpi=dpi)

def ocr(path_or_bytes: str | IO[bytes]):
    reader = easyocr.Reader(["en"], gpu=True)

    result = reader.readtext(path_or_bytes)

    def box_to_polygon(box):
        """Return list of tuples [(x,y), ...] as ints for PIL polygon drawing"""
        return [(int(p[0]), int(p[1])) for p in box]

    img = Image.open(path_or_bytes).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)

    box_color = (0, 200, 0, 255)
    line_width = 2

    out = []
    for det in result:
        box, text, _ = det
        poly = box_to_polygon(box)

        draw.line(poly + [poly[0]], fill=box_color, width=line_width)
        out.append(text)

    result = Image.alpha_composite(img, overlay).convert("RGB")

    # Save result
    result.save("image_with_boxes.jpg", quality=100)

    # Show with matplotlib
    plt.figure(figsize=(10, 8))
    plt.imshow(result)
    plt.axis("off")
    plt.tight_layout()
    return out
