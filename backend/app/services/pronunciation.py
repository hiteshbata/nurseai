import tempfile
import asyncio
from typing import Dict, Any, List
from app.core.config import settings

# Azure Speech SDK
# Install: pip install azure-cognitiveservices-speech

AZURE_SPEECH_KEY = settings.AZURE_SPEECH_KEY
AZURE_SPEECH_REGION = settings.AZURE_SPEECH_REGION

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
    """
    try:
        import azure.cognitiveservices.speech as speechsdk
        
        if not AZURE_SPEECH_KEY:
            return {
                "error": "Azure Speech key not configured",
                "available": False
            }
        
        # Save audio to temp file
        suffix = f".{audio_format}"
        with tempfile.NamedTemporaryFile(
            suffix=suffix, 
            delete=False
        ) as tmp:
            tmp.write(audio_data)
            tmp_path = tmp.name
        
        # Configure Azure Speech
        speech_config = speechsdk.SpeechConfig(
            subscription=AZURE_SPEECH_KEY,
            region=AZURE_SPEECH_REGION
        )
        speech_config.speech_recognition_language = "en-US"
        
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
        
        # Run recognition
        result = recognizer.recognize_once()
        
        # Clean up temp file
        os.unlink(tmp_path)
        
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
            return {
                "available": True,
                "error": f"Recognition failed: {result.reason}",
                "overall_score": 0,
                "words": [],
                "problem_words": []
            }
            
    except ImportError:
        return {
            "error": "Azure Speech SDK not installed. Run: pip install azure-cognitiveservices-speech",
            "available": False
        }
    except Exception as e:
        return {
            "error": str(e),
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
        # Azure not configured — use pattern analysis only
        return {
            "method": "pattern_analysis",
            "azure": None,
            "pattern_analysis": pattern_findings,
            "has_azure": False,
            "message": "Add AZURE_SPEECH_KEY to .env for word-level scoring"
        }
