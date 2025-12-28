import dotenv
import os

from tavily import TavilyClient

from typing import Literal, Optional, Any

from annotated_types import Ge, Le


from typing import Annotated

from pydantic import StringConstraints

Date = Annotated[
    str,
    StringConstraints(pattern=r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$"),
    "Date in a YYYY-MM-DD format.",
]


ZeroToTwenty = Annotated[int, Ge(0), Le(20), "Any number from 0 to 20"]


env = dotenv.load_dotenv()


api_key = os.getenv("TAVILY_API_KEY")


tavily_client = TavilyClient(api_key=api_key)


def search(
    query: str,
    topic: Optional[Literal["general", "news", "finance"]] = None,
    time_range: Optional[Literal["day", "week", "month", "year"]] = None,
    start_date: Optional[Date] = None,
    end_date: Optional[Date] = None,
    max_results: Optional[ZeroToTwenty] = None,
    include_images: bool = False,
    include_image_descriptions: bool = False,
    include_domains: Optional[list[str]] = None,
    exclude_domains: Optional[list[str]] = None,
) -> list[dict[str, Any]] | tuple[list[dict[str, Any]], list[dict[str, str]]]:
    args: dict[str, Any] = {}

    if topic:
        args["topic"] = topic

    if time_range:
        args["time_range"] = time_range

    if start_date:
        args["start_date"] = start_date

    if end_date:
        args["end_date"] = end_date

    if max_results:
        args["max_results"] = max_results

    if include_images:
        args["include_images"] = include_images

    if include_image_descriptions:
        args["include_image_descriptions"] = include_image_descriptions

    if include_domains:
        args["include_domains"] = include_domains

    if exclude_domains:
        args["exclude_domains"] = exclude_domains

    response = tavily_client.search(query, **args)

    image_responses = []

    if include_images or include_image_descriptions:
        image_responses = response["images"]

        return response["results"], image_responses

    return response["results"]


def visit(
    url: str | list[str], include_images: bool = False
) -> list[dict[str, str | list]]:
    if isinstance(url, str):
        url = [url]

    url: list[str] = [url] if isinstance(url, str) else url

    response = tavily_client.extract(
        url, include_images=include_images, extract_depth="advanced"
    )
    return response["results"]
