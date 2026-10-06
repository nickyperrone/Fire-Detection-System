"""Listing and downloading GOES files from NOAA's public S3 bucket (no credentials)."""

import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta

import httpx

S3_NAMESPACE = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
# OR_ABI-L2-FDCF-M6_G19_s20262781620211_e…: satellite, then the scan start as year, day of the
# year, hour, minute, second and tenth of a second.
KEY_PATTERN = re.compile(r"_G(\d+)_s(\d{4})(\d{3})(\d{2})(\d{2})(\d{2})\d")


def scan_of_key(key: str) -> tuple[str, datetime]:
    """The satellite ("GOES-19") and scan start of an ABI or GLM file, from its name."""
    match = KEY_PATTERN.search(key)
    if match is None:
        raise ValueError(f"not a GOES file name: {key}")
    number, year, day, hour, minute, second = (int(g) for g in match.groups())
    start = datetime(year, 1, 1, hour, minute, second, tzinfo=UTC) + timedelta(days=day - 1)
    return f"GOES-{number}", start


def bucket_url(bucket: str) -> str:
    return f"https://{bucket}.s3.amazonaws.com"


def hour_prefixes(product: str, now: datetime, hours_back: int = 1) -> list[str]:
    """The current hour and the `hours_back` before it, oldest first: a file can be published
    after its hour ends."""
    return [f"{product}/{now - timedelta(hours=h):%Y/%j/%H}/" for h in range(hours_back, -1, -1)]


def list_keys(client: httpx.Client, bucket: str, prefix: str) -> list[str]:
    keys: list[str] = []
    params = {"list-type": "2", "prefix": prefix}
    while True:
        response = client.get(bucket_url(bucket), params=params, timeout=30)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        keys += [k.text for k in root.findall("s3:Contents/s3:Key", S3_NAMESPACE) if k.text]
        token = root.find("s3:NextContinuationToken", S3_NAMESPACE)
        if token is None or not token.text:
            return keys
        params["continuation-token"] = token.text


def new_keys(
    client: httpx.Client,
    bucket: str,
    product: str,
    now: datetime,
    cursor: str | None,
    first_run: int,
) -> list[str]:
    """Keys after the cursor, oldest first. Key names start with the scan time, so they sort.

    Without a cursor only the newest `first_run` files are taken, not two hours of backlog.
    """
    keys = sorted(
        k for prefix in hour_prefixes(product, now) for k in list_keys(client, bucket, prefix)
    )
    if cursor is None:
        return keys[-first_run:]
    return [k for k in keys if k > cursor]


def download(client: httpx.Client, bucket: str, key: str) -> bytes:
    response = client.get(f"{bucket_url(bucket)}/{key}", timeout=60)
    response.raise_for_status()
    return response.content
