from fastapi import FastAPI, HTTPException, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
import lameenc
import uuid
from threading import Lock
import dashscope
from dashscope.audio.asr import *
import os
from dotenv import load_dotenv

load_dotenv()


def init_dashscope_api_key():
    if 'DASHSCOPE_API_KEY' in os.environ:
        dashscope.api_key = os.environ['DASHSCOPE_API_KEY']
    else:
        dashscope.api_key = '<your-dashscope-api-key>'


init_dashscope_api_key()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

sessions = {}
session_lock = Lock()


class RecordingSession:
    def __init__(self):
        self.encoder = lameenc.Encoder()
        self.encoder.set_bit_rate(128)
        self.encoder.set_in_sample_rate(16000)
        self.encoder.set_channels(1)
        self.encoder.set_quality(2)
        self.mp3_data = bytearray()
        self.recognition = None
        self.results = []
        self.results_lock = Lock()


class SessionCallback(TranslationRecognizerCallback):
    def __init__(self, session):
        super().__init__()
        self.session = session

    def on_event(self, request_id, transcription_result: TranscriptionResult, translation_result: TranslationResult, usage) -> None:
        translation_text = ""
        rec_text = ""
        if translation_result is not None:
            english_translation = translation_result.get_translation("en")
            translation_text = english_translation.text
        if transcription_result is not None:
            rec_text = transcription_result.text
        with self.session.results_lock:
            self.session.results.append(translation_text + rec_text)
        


@app.post("/start_recording")
def start_recording():
    session_id = str(uuid.uuid4())
    with session_lock:
        session = RecordingSession()
        # 创建识别实例并绑定会话回调
        session.recognition = TranslationRecognizerRealtime(
            model="gummy-realtime-v1",
            format='pcm',
            sample_rate=16000,
            transcription_enabled=True,
            translation_enabled=True,
            translation_target_languages=["en"],
            callback=SessionCallback(session)
        )
        session.recognition.start()
        sessions[session_id] = session
    return {"session_id": session_id}


@app.post("/upload_audio/{session_id}")
async def upload_audio(session_id: str, data: UploadFile = File(...)):
    with session_lock:
        session = sessions.get(session_id)
        if not session:
            raise HTTPException(404, "Session not found")

        pcm_data = await data.read()
        session.recognition.send_audio_frame(pcm_data)

        mp3_chunk = session.encoder.encode(pcm_data)
        session.mp3_data.extend(mp3_chunk)

        # 获取并清空当前结果
        with session.results_lock:
            results = session.results.copy()
            session.results.clear()

    return {"status": "ok", "results": results}


@app.post("/stop_recording/{session_id}")
async def stop_recording(session_id: str):
    with session_lock:
        session = sessions.pop(session_id, None)
        if not session:
            raise HTTPException(404, "Session not found")

        session.recognition.stop()
        session.mp3_data.extend(session.encoder.flush())
        if not os.path.exists("./recordings"):
            os.makedirs("./recordings")
        with open(f"./recordings/{session_id}.mp3", "wb") as f:
            f.write(session.mp3_data)

        # 获取最终结果
        with session.results_lock:
            final_results = session.results.copy()
            session.results.clear()

    return {"status": "saved", "results": final_results}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)