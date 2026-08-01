import re
from datetime import datetime

# Regular expressions for common date formats
DATE_PATTERNS = [
    r"\b\d{1,2}/\d{1,2}/\d{4}\b",          # 17/07/2026
    r"\b\d{1,2}-\d{1,2}-\d{4}\b",          # 17-07-2026
    r"\b\d{4}\b",                          # 2005
    r"\b\d{1,2}\s+[A-Za-z]+\s+\d{4}\b"     # 17 July 2026
]


def extract_timeline_events(results):
    """
    Extract timeline events from Chroma search results.

    Parameters
    ----------
    results : dict
        Results returned from collection.query()

    Returns
    -------
    list
        List of timeline events.
    """

    events = []

    if not results["documents"]:
        return events

    for i in range(len(results["documents"][0])):

        text = results["documents"][0][i]

        metadata = results["metadatas"][0][i]

        for pattern in DATE_PATTERNS:

            matches = re.findall(pattern, text)

            for match in matches:

                events.append({
                    "date": match,
                    "event": text[:250] + "...",
                    "file": metadata["file"],
                    "page": metadata["page"]
                })

    return events


def sort_events(events):
    """
    Sort events by date where possible.
    """

    def parse_date(value):

        formats = [
            "%d/%m/%Y",
            "%d-%m-%Y",
            "%d %B %Y",
            "%Y"
        ]

        for fmt in formats:

            try:
                return datetime.strptime(value, fmt)

            except ValueError:
                pass

        return datetime.max

    return sorted(events, key=lambda x: parse_date(x["date"]))