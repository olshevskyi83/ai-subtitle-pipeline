import os
import time
import shutil
import logging
from pathlib import Path
from datetime import timedelta
from status import write_status

import srt
from dotenv import load_dotenv
from faster_whisper import WhisperModel
from openai import OpenAI


load_dotenv()

INCOMING_DIR = Path(os.getenv("INCOMING_DIR", "/data/incoming"))
PROCESSING_DIR = Path(os.getenv("PROCESSING_DIR", "/data/processing"))
READY_DIR = Path(os.getenv("READY_DIR", "/data/ready"))
FAILED_DIR = Path(os.getenv("FAILED_DIR", "/data/failed"))
STATUS_DIR = Path(os.getenv("STATUS_DIR", "/data/logs/status"))

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "medium")
SOURCE_LANGUAGE = os.getenv("SOURCE_LANGUAGE", "uk")
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "10"))
STABLE_SECONDS = int(os.getenv("STABLE_SECONDS", "20"))
OPENAI_TRANSLATION_MODEL = os.getenv("OPENAI_TRANSLATION_MODEL", "gpt-4.1-mini")

VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler("/app/logs/subtitle-pipeline.log"),
        logging.StreamHandler()
    ],
)

client = OpenAI()

logging.info(f"Loading Faster-Whisper model: {WHISPER_MODEL}")
model = WhisperModel(
    WHISPER_MODEL,
    device="cpu",
    compute_type="int8"
)
logging.info("Model loaded.")


def is_video(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS


def is_file_stable(path: Path) -> bool:
    size1 = path.stat().st_size
    time.sleep(STABLE_SECONDS)
    if not path.exists():
        return False
    size2 = path.stat().st_size
    return size1 == size2


def format_srt_timestamp(seconds: float) -> timedelta:
    return timedelta(seconds=max(0, seconds))


def transcribe_to_srt(video_path: Path, output_srt: Path):
    logging.info(f"Transcribing CapCut-style: {video_path.name}")

    segments, info = model.transcribe(
        str(video_path),
        language=SOURCE_LANGUAGE,
        beam_size=5,
        vad_filter=True,
        word_timestamps=True,
        condition_on_previous_text=True,
        temperature=0.0,
    )

    subtitles = []
    index = 1

    max_words = 4
    max_duration = 2.2

    current_words = []
    start_time = None
    end_time = None

    def flush():
        nonlocal index, current_words, start_time, end_time

        if not current_words or start_time is None or end_time is None:
            return

        text = " ".join(current_words).strip()

        subtitles.append(
            srt.Subtitle(
                index=index,
                start=format_srt_timestamp(start_time),
                end=format_srt_timestamp(end_time),
                content=text,
            )
        )

        index += 1
        current_words = []
        start_time = None
        end_time = None

    for segment in segments:
        if not segment.words:
            continue

        for word in segment.words:
            clean_word = word.word.strip()

            if not clean_word:
                continue

            if start_time is None:
                start_time = word.start

            current_words.append(clean_word)
            end_time = word.end

            duration = end_time - start_time

            should_flush = (
                len(current_words) >= max_words
                or duration >= max_duration
                or clean_word.endswith((".", "!", "?", "…"))
            )

            if should_flush:
                flush()

    flush()

    output_srt.write_text(srt.compose(subtitles), encoding="utf-8")
    logging.info(f"Created CapCut-style Ukrainian SRT: {output_srt.name}")

def translate_block(text: str) -> str:
    response = client.responses.create(
        model=OPENAI_TRANSLATION_MODEL,
        input=[
            {
                "role": "system",
                "content": (
                    "You translate Ukrainian subtitles into natural English. "
                    "Preserve SRT numbering, timestamps, blank lines, and formatting exactly. "
                    "Translate only subtitle text. Do not add comments."
                ),
            },
            {
                "role": "user",
                "content": text,
            },
        ],
    )

    return response.output_text.strip() + "\n"


def translate_srt_uk_to_en(input_srt: Path, output_srt: Path):
    logging.info(f"Translating SRT to English: {input_srt.name}")

    text = input_srt.read_text(encoding="utf-8")

    # Для коротких TikTok/Reels можна одним блоком.
    # Якщо буде довге відео — пізніше додамо chunking.
    translated = translate_block(text)

    output_srt.write_text(translated, encoding="utf-8")
    logging.info(f"Created English SRT: {output_srt.name}")


def marker_path(video_path: Path) -> Path:
    return READY_DIR / f"{video_path.stem}.done"


def already_processed(video_path: Path) -> bool:
    return marker_path(video_path).exists()


def process_video(incoming_video: Path):
    if already_processed(incoming_video):
        logging.info(f"Skipping already processed file: {incoming_video.name}")
        return

    logging.info(f"New file detected: {incoming_video.name}")

    write_status(
        STATUS_DIR,
        incoming_video.stem,
        "uploaded",
        5,
        "File uploaded. Waiting until upload is stable."
    )

    if not is_file_stable(incoming_video):
        logging.warning(f"File is not stable yet: {incoming_video.name}")
        return

    processing_video = PROCESSING_DIR / incoming_video.name

    try:
        write_status(
            STATUS_DIR,
            incoming_video.stem,
            "processing",
            15,
            "Moving file to processing."
        )

        shutil.move(str(incoming_video), str(processing_video))
        logging.info(f"Moved to processing: {processing_video.name}")

        uk_srt = READY_DIR / f"{processing_video.stem}.uk.srt"
        en_srt = READY_DIR / f"{processing_video.stem}.en.srt"
        
        write_status(
            STATUS_DIR,
            processing_video.stem,
            "transcribing",
            35,
            "Generating Ukrainian subtitles."
        )

        transcribe_to_srt(processing_video, uk_srt)

        write_status(
            STATUS_DIR,
            processing_video.stem,
            "translating",
            70,
            "Translating subtitles to English."
        )

        translate_srt_uk_to_en(uk_srt, en_srt)
        
        write_status(
            STATUS_DIR,
            processing_video.stem,
            "done",
            100,
            "Subtitles are ready."
        )

        marker_path(processing_video).write_text(
            f"processed={processing_video.name}\n",
            encoding="utf-8"
        )

        logging.info(f"Done: {processing_video.name}")

        processing_video.unlink()

    except Exception as e:
        logging.exception(f"Failed processing {incoming_video.name}: {e}")

        write_status(
            STATUS_DIR,
            incoming_video.stem,
            "failed",
            100,
            str(e)
        )

        failed_target = FAILED_DIR / incoming_video.name
        if processing_video.exists():
            shutil.move(str(processing_video), str(failed_target))
        elif incoming_video.exists():
            shutil.move(str(incoming_video), str(failed_target))

def main():
    logging.info("AI Subtitle Pipeline started.")

    for directory in [INCOMING_DIR, PROCESSING_DIR, READY_DIR, FAILED_DIR, STATUS_DIR]:
        directory.mkdir(parents=True, exist_ok=True)

    while True:
        try:
            files = sorted(INCOMING_DIR.iterdir(), key=lambda p: p.stat().st_mtime)

            for file in files:
                if is_video(file):
                    process_video(file)

        except Exception as e:
            logging.exception(f"Main loop error: {e}")

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
