from abc import ABC, abstractmethod


class RealCamera(ABC):
    """
    Abstract base class for real camera
    """

    @abstractmethod
    def open(self):
        pass

    @abstractmethod
    def close(self):
        pass

    @abstractmethod
    def read_frame(self):
        pass

    @property
    @abstractmethod
    def flip(self):
        pass


