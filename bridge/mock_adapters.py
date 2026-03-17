from __future__ import annotations

from dataclasses import dataclass, field

from bridge.models import WorkItem


@dataclass
class InMemoryPaperclip:
    items: dict[str, WorkItem] = field(default_factory=dict)

    def list_items(self) -> list[WorkItem]:
        return list(self.items.values())

    def set_status(self, item_id: str, status: str) -> None:
        item = self.items[item_id]
        self.items[item_id] = WorkItem(id=item.id, status=status, assignee=item.assignee, raw=item.raw)

    def get_item(self, item_id: str) -> WorkItem:
        return self.items[item_id]


@dataclass
class InMemoryBeads:
    items: dict[str, WorkItem] = field(default_factory=dict)

    def list_items(self) -> list[WorkItem]:
        return list(self.items.values())

    def set_status(self, item_id: str, status: str) -> None:
        item = self.items[item_id]
        self.items[item_id] = WorkItem(id=item.id, status=status, assignee=item.assignee, raw=item.raw)

    def get_item(self, item_id: str) -> WorkItem:
        return self.items[item_id]


@dataclass
class InMemoryGastown:
    attached: list[tuple[str, str]] = field(default_factory=list)

    def attach_hook(self, issue_id: str, assignee: str) -> str:
        self.attached.append((issue_id, assignee))
        return f"hook-{issue_id}-{assignee}"
