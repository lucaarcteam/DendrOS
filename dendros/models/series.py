from dataclasses import dataclass, field
from typing import Optional
import numpy as np


@dataclass
class Series:
    name: str
    years: np.ndarray
    values: np.ndarray
    filename: str = ""
    species: str = ""
    notes: str = ""
    indices: Optional[np.ndarray] = None
    detrend_method: str = ""

    def __post_init__(self):
        if isinstance(self.years, list):
            self.years = np.array(self.years)
        if isinstance(self.values, list):
            self.values = np.array(self.values)
        if isinstance(self.indices, list):
            self.indices = np.array(self.indices)

    def has_indices(self) -> bool:
        return self.indices is not None and len(self.indices) > 0

    @property
    def start_year(self) -> int:
        return int(self.years[0])

    @property
    def end_year(self) -> int:
        return int(self.years[-1])

    @property
    def length(self) -> int:
        return len(self.years)

    def __len__(self) -> int:
        return self.length
