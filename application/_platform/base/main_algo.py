from abc import abstractmethod, ABC


class MainAlgo(ABC):
    """
    Abstract base class for main_algo i.e. algorithm to process input and generate output with redirected face and gaze.
    
    """

    @abstractmethod
    def process_frame(self, cropped_roi, is_test_frame):
        pass
