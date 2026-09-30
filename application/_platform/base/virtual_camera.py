from abc import ABC, abstractmethod


class VirtualCamera(ABC):
    """
    Abstract base class for Virtual Camera
    """

    @property
    @abstractmethod
    def resolution(self):
        pass

    @abstractmethod
    def close(self):
        pass

    @abstractmethod
    def write_frame(self, image):
        pass
