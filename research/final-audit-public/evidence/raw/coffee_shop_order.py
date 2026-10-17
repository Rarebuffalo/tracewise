"""Order model — a customer's list of items with optional extras."""

from dataclasses import dataclass, field
from typing import List


@dataclass
class OrderItem:
    menu_item_name: str
    quantity: int = 1
    extras: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.quantity < 1:
            raise ValueError(f"Quantity must be at least 1, got {self.quantity}")


@dataclass
class Order:
    customer_name: str
    items: List[OrderItem] = field(default_factory=list)

    def add_item(self, item: OrderItem) -> None:
        self.items.append(item)

    def item_count(self) -> int:
        return sum(i.quantity for i in self.items)

    def is_empty(self) -> bool:
        return len(self.items) == 0
