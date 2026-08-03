import logging
import os
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Dict, Any, List
from app.core.config import settings
from app.core.threading import run_sync

# The Azure Speech SDK's recognize_once() is a blocking native call with no
# built-in timeout -- a stalled/unresponsive Azure connection would otherwise
# hang the worker thread run_sync already dispatched this onto indefinitely.
PRONUNCIATION_RECOGNIZE_TIMEOUT_SECONDS = 30

# Azure Speech SDK
# Install: pip install azure-cognitiveservices-speech

logger = logging.getLogger(__name__)

AZURE_SPEECH_KEY = settings.AZURE_SPEECH_KEY
AZURE_SPEECH_REGION = settings.AZURE_SPEECH_REGION

# Generic, user-safe message shown whenever Azure phoneme-level scoring
# couldn't run for any reason -- the real cause (missing key, SDK error,
# transcoding failure, etc.) is logged server-side only, never returned
# to the client, since earlier versions leaked setup instructions like
# "Add AZURE_SPEECH_KEY to .env" straight into the results page.
PRONUNCIATION_UNAVAILABLE_MESSAGE = "Pronunciation analysis is currently unavailable."

# Common Indian English pronunciation 
# patterns to flag specifically
INDIAN_ACCENT_PATTERNS = {
    "v_w_confusion": {
        "description": "V and W sound confusion",
        "examples": {
            "wery": "very",
            "waccine": "vaccine", 
            "wein": "vein",
            "wital": "vital",
            "womit": "vomit",
            "wentilator": "ventilator",
            "waccination": "vaccination",
        }
    },
    "th_confusion": {
        "description": "TH sound replaced with D or T",
        "examples": {
            "dis": "this",
            "dese": "these", 
            "dere": "there",
            "dat": "that",
            "dem": "them",
            "tree": "three",
            "tink": "think",
            "trough": "through",
            "wid": "with",
            "widhout": "without",
        }
    },
    "word_endings": {
        "description": "Word ending sounds dropped",
        "examples": {
            "jus": "just",
            "tes": "test",
            "bes": "best",
            "fas": "fast",
            "las": "last",
            "firs": "first",
            "nex": "next",
        }
    },
    "vowel_sounds": {
        "description": "Vowel sound differences",
        "examples": {
            "medicin": "medicine",
            "pacient": "patient",
            "informasion": "information",
            "situasion": "situation",
            "educasion": "education",
        }
    }
}

async def assess_pronunciation_azure(
    audio_data: bytes,
    audio_format: str = "webm",
    reference_text: str = ""
) -> Dict[str, Any]:
    """
    Send audio to Azure Pronunciation Assessment API.
    Returns word-level pronunciation scores.

    The Azure SDK call itself is fully synchronous (recognize_once() blocks
    for the whole recognition round trip), so it runs in a worker thread via
    run_sync instead of on the event loop.
    """
    return await run_sync(
        _assess_pronunciation_azure_sync, audio_data, audio_format, reference_text
    )


def _transcode_to_wav(audio_data: bytes, audio_format: str) -> str:
    """Transcode arbitrary browser-recorded audio (webm/ogg/mp4/...) to the
    16kHz mono PCM WAV Azure's AudioConfig(filename=...) actually requires --
    it only accepts WAV by default and does not auto-detect/decode compressed
    containers, so handing it a raw webm/mp3 file fails with SPXERR_INVALID_HEADER
    regardless of the file's suffix. Returns the path to the WAV temp file;
    caller is responsible for deleting it."""
    src_fd, src_path = tempfile.mkstemp(suffix=f".{audio_format}")
    dst_fd, dst_path = tempfile.mkstemp(suffix=".wav")
    os.close(src_fd)
    os.close(dst_fd)
    try:
        with open(src_path, "wb") as f:
            f.write(audio_data)
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", src_path,
                "-ar", "16000", "-ac", "1", "-f", "wav", dst_path,
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )
    finally:
        os.unlink(src_path)
    return dst_path


def _assess_pronunciation_azure_sync(
    audio_data: bytes,
    audio_format: str = "webm",
    reference_text: str = ""
) -> Dict[str, Any]:
    try:
        import azure.cognitiveservices.speech as speechsdk

        if not AZURE_SPEECH_KEY:
            logger.error("[PRONUNCIATION_FAILURE] AZURE_SPEECH_KEY is not configured")
            return {
                "error": PRONUNCIATION_UNAVAILABLE_MESSAGE,
                "available": False
            }

        try:
            tmp_path = _transcode_to_wav(audio_data, audio_format)
        except subprocess.CalledProcessError as e:
            logger.error(
                "[PRONUNCIATION_FAILURE] audio transcoding failed: %s",
                e.stderr.decode(errors="replace")[:500],
            )
            return {
                "error": PRONUNCIATION_UNAVAILABLE_MESSAGE,
                "available": False,
                "overall_score": 0,
                "words": [],
                "problem_words": [],
            }

        recognizer = None
        audio_config = None
        try:
            # Configure Azure Speech
            speech_config = speechsdk.SpeechConfig(
                subscription=AZURE_SPEECH_KEY,
                region=AZURE_SPEECH_REGION
            )
            # en-IN, not en-US: matches the accent our nursing students
            # actually speak (same reasoning as the Deepgram streaming STT
            # locale choice in speaking.py's /stt/stream).
            speech_config.speech_recognition_language = "en-IN"

            # Configure Pronunciation Assessment
            pronunciation_config = speechsdk.PronunciationAssessmentConfig(
                reference_text=reference_text,
                grading_system=speechsdk.PronunciationAssessmentGradingSystem.HundredMark,
                granularity=speechsdk.PronunciationAssessmentGranularity.Word,
                enable_miscue=True
            )

            # Create audio config from file
            audio_config = speechsdk.AudioConfig(filename=tmp_path)

            # Create recognizer
            recognizer = speechsdk.SpeechRecognizer(
                speech_config=speech_config,
                audio_config=audio_config
            )
            pronunciation_config.apply_to(recognizer)

            # Run recognition, bounded -- see PRONUNCIATION_RECOGNIZE_TIMEOUT_SECONDS.
            # shutdown(wait=False) on timeout: recognize_once() can't be
            # cancelled mid-call, so we abandon the thread instead of
            # blocking the caller on it too.
            pool = ThreadPoolExecutor(max_workers=1)
            try:
                result = pool.submit(recognizer.recognize_once).result(timeout=PRONUNCIATION_RECOGNIZE_TIMEOUT_SECONDS)
            except FutureTimeoutError:
                logger.error("[PRONUNCIATION_FAILURE] recognize_once timed out after %ss", PRONUNCIATION_RECOGNIZE_TIMEOUT_SECONDS)
                pool.shutdown(wait=False)
                return {
                    "error": PRONUNCIATION_UNAVAILABLE_MESSAGE,
                    "available": False,
                    "overall_score": 0,
                    "words": [],
                    "problem_words": [],
                }
            pool.shutdown(wait=False)
        finally:
            # Dispose the recognizer/audio_config first so the native SDK
            # releases its file handle before we unlink -- otherwise deleting
            # the temp file here can raise (observed as WinError 32 on
            # Windows) and mask whatever the actual recognition result was.
            del recognizer
            del audio_config
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        if result.reason == speechsdk.ResultReason.RecognizedSpeech:
            pronunciation_result = speechsdk.PronunciationAssessmentResult(result)
            
            # Extract word-level results
            words = []
            for word in pronunciation_result.words:
                words.append({
                    "word": word.word,
                    "accuracy_score": round(word.accuracy_score, 1),
                    "error_type": str(word.error_type) if hasattr(word, 'error_type') else "None"
                })
            
            # Find problematic words (score < 60)
            problem_words = [
                w for w in words 
                if w["accuracy_score"] < 60
            ]
            
            return {
                "available": True,
                "overall_score": round(
                    pronunciation_result.accuracy_score, 1
                ),
                "fluency_score": round(
                    pronunciation_result.fluency_score, 1
                ),
                "completeness_score": round(
                    pronunciation_result.completeness_score, 1
                ),
                "words": words,
                "problem_words": problem_words,
                "transcript": result.text
            }
        else:
            logger.warning("[PRONUNCIATION_FAILURE] recognition failed: %s", result.reason)
            return {
                "available": False,
                "error": PRONUNCIATION_UNAVAILABLE_MESSAGE,
                "overall_score": 0,
                "words": [],
                "problem_words": []
            }

    except ImportError:
        logger.error("[PRONUNCIATION_FAILURE] azure-cognitiveservices-speech is not installed")
        return {
            "error": PRONUNCIATION_UNAVAILABLE_MESSAGE,
            "available": False
        }
    except Exception as e:
        logger.error("[PRONUNCIATION_FAILURE] unexpected error: %s", str(e))
        return {
            "error": PRONUNCIATION_UNAVAILABLE_MESSAGE,
            "available": False,
            "overall_score": 0,
            "words": [],
            "problem_words": []
        }


def analyze_indian_patterns(transcript: str) -> List[Dict[str, Any]]:
    """
    Analyze transcript text for common Indian 
    English pronunciation patterns.
    Used as fallback when Azure is unavailable.
    """
    findings = []
    transcript_lower = transcript.lower()
    words_in_transcript = transcript_lower.split()
    
    for pattern_key, pattern_data in INDIAN_ACCENT_PATTERNS.items():
        for wrong, correct in pattern_data["examples"].items():
            if wrong in words_in_transcript:
                findings.append({
                    "pattern": pattern_data["description"],
                    "word_said": wrong,
                    "word_correct": correct,
                    "tip": f"Practice saying '{correct}' — "
                           f"focus on the sound difference"
                })
    
    return findings


async def get_pronunciation_feedback(
    audio_data: bytes,
    nurse_transcript: str,
    audio_format: str = "webm"
) -> Dict[str, Any]:
    """
    Main function — tries Azure first,
    falls back to pattern analysis.
    """
    # Always run pattern analysis on transcript
    pattern_findings = analyze_indian_patterns(nurse_transcript)
    
    # Try Azure if key is configured
    if AZURE_SPEECH_KEY:
        azure_result = await assess_pronunciation_azure(
            audio_data=audio_data,
            audio_format=audio_format,
            reference_text=nurse_transcript
        )
        
        return {
            "method": "azure",
            "azure": azure_result,
            "pattern_analysis": pattern_findings,
            "has_azure": True
        }
    else:
        # Azure not configured — use pattern analysis only. Elite users hitting
        # this path means the plan grants Azure access but the server-side key
        # is missing, which is an ops problem, not something to surface to the user.
        logger.error("[PRONUNCIATION_FAILURE] AZURE_SPEECH_KEY is not configured")
        return {
            "method": "pattern_analysis",
            "azure": None,
            "pattern_analysis": pattern_findings,
            "has_azure": False,
            "message": PRONUNCIATION_UNAVAILABLE_MESSAGE,
        }
