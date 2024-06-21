import cv2

class VideoCamera:
    def __init__(self):
        self.video = cv2.VideoCapture(0)  # Ganti 0 dengan URL RTSP kalo butuh

    def __del__(self):
        self.video.release()

    def get_frame(self):
        success, image = self.video.read()
        ret, jpeg = cv2.imencode('.jpg', image)
        return jpeg.tobytes(), image  # Mengembalikan frame untuk pemrosesan lanjutan
