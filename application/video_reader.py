import cv2

class VideoReader:
    def __init__(self, video_path):
        self.video_path = video_path
        self._initialize_video()

    def _initialize_video(self):
        self.cap = cv2.VideoCapture(self.video_path)
        if not self.cap.isOpened():
            raise ValueError("Cannot open the video file.")

    def read_next_frame(self):
        ret, frame = self.cap.read()
        if not ret:
            self.cap.release()
            self._initialize_video()
            ret, frame = self.cap.read()
            if not ret:
                return None
        return frame

    def release(self):
        self.cap.release()
