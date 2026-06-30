from dataclasses import dataclass, field
from typing import Optional
import numpy as np
from .series import Series


@dataclass
class Project:
    name: str
    description: str = ""
    series_list: list[Series] = field(default_factory=list)

    def add_series(self, series: Series):
        self.series_list.append(series)

    def remove_series(self, name: str):
        self.series_list = [s for s in self.series_list if s.name != name]

    def get_series(self, name: str) -> Optional[Series]:
        for s in self.series_list:
            if s.name == name:
                return s
        return None

    @property
    def series_count(self) -> int:
        return len(self.series_list)

    def __len__(self) -> int:
        return self.series_count
