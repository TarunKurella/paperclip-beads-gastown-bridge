from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from bridge.models import WorkItem


class PaperclipAdapter(Protocol):
    def list_items(self) -> list[WorkItem]: ...

    def set_status(self, item_id: str, status: str) -> None: ...

    def get_item(self, item_id: str) -> WorkItem: ...


class BeadsAdapter(Protocol):
    def list_items(self) -> list[WorkItem]: ...

    def set_status(self, item_id: str, status: str) -> None: ...

    def get_item(self, item_id: str) -> WorkItem: ...


class GastownAdapter(Protocol):
    def attach_hook(self, issue_id: str, assignee: str) -> str: ...


@dataclass
class AdapterBundle:
    paperclip: PaperclipAdapter
    beads: BeadsAdapter
    gastown: GastownAdapter
