import os
import cv2
import requests
import base64
from PIL import Image, ImageDraw
from io import BytesIO
from roboflow import Roboflow

API_KEY = "5xBjcLVwrOxJ9N7OHXEJ"
MODEL_ENDPOINT = "people-object-detection-rxb7e"
VERSION = 3

# Inisialisasi Roboflow
rf = Roboflow(api_key=API_KEY)
project = rf.workspace().project(MODEL_ENDPOINT)
model = project.version(VERSION).model

def detect_objects(frame):
    try:
        # Encode frame ke JPG
        _, buffer = cv2.imencode('.jpg', frame)
        img_str = base64.b64encode(buffer).decode('utf-8')

        # Request ke API
        response = requests.post(
            f"https://detect.roboflow.com/{MODEL_ENDPOINT}/{VERSION}",
            params={
                "api_key": API_KEY,
                "confidence": 50,
                "overlap": 60,
                "format": "json"
            },
            data=img_str,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        predictions = response.json()
        return predictions
    except Exception as e:
        print(f"An error occurred: {e}")
        return None
