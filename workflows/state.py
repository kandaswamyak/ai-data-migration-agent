from typing import TypedDict


class MigrationState(TypedDict):

    source: str

    target: str

    status: str
