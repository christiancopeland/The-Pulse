"""
Audio Generator for The Pulse.

SYNTH-004: Piper TTS Integration

Generates audio briefings using Piper TTS for text-to-speech.
https://github.com/rhasspy/piper
"""
from typing import Optional
from pathlib import Path
import asyncio
import subprocess
import logging
import re
import os
import shutil

logger = logging.getLogger(__name__)

# Piper voice data directory
PIPER_DATA_DIR = Path.home() / '.local' / 'share' / 'piper'


class AudioGenerationError(Exception):
    """Exception raised for audio generation errors."""
    pass


class AudioGenerator:
    """
    Generates audio briefings using Piper TTS.

    Piper is a fast, local neural text-to-speech system.
    Install with: pip install piper-tts
    Download voice models from: https://github.com/rhasspy/piper/releases
    """

    # Default voice model (must be installed locally)
    DEFAULT_VOICE = "en_US-lessac-medium"

    # Text preparation patterns
    MARKDOWN_PATTERNS = [
        (r'\*\*([^*]+)\*\*', r'\1'),  # Bold
        (r'\*([^*]+)\*', r'\1'),       # Italic
        (r'#+ ', ''),                   # Headers
        (r'\[([^\]]+)\]\([^)]+\)', r'\1'),  # Links
        (r'^\s*[-*] ', ''),             # List items
        (r'^\s*\d+\. ', ''),            # Numbered lists
        (r'---+', ''),                  # Horizontal rules
        (r'`([^`]+)`', r'\1'),          # Inline code
    ]

    # Abbreviation expansions for better TTS
    ABBREVIATIONS = {
        "e.g.": "for example",
        "i.e.": "that is",
        "etc.": "et cetera",
        "vs.": "versus",
        "Dr.": "Doctor",
        "Mr.": "Mister",
        "Mrs.": "Missus",
        "Ms.": "Miss",
        "Inc.": "Incorporated",
        "Corp.": "Corporation",
        "Ltd.": "Limited",
        "AI": "A.I.",
        "ML": "M.L.",
        "API": "A.P.I.",
        "URL": "U.R.L.",
        "UTC": "U.T.C.",
        "US": "U.S.",
        "USA": "U.S.A.",
        "UK": "U.K.",
    }

    def __init__(
        self,
        voice_model: Optional[str] = None,
        output_dir: Optional[str] = None,
        piper_path: Optional[str] = None,
    ):
        """
        Initialize audio generator.

        Args:
            voice_model: Piper voice model to use
            output_dir: Directory for audio output files
            piper_path: Path to piper executable (auto-detected if not specified)
        """
        self.voice_model = voice_model or os.getenv(
            "PIPER_VOICE",
            self.DEFAULT_VOICE
        )
        self.output_dir = Path(
            output_dir or os.getenv("AUDIO_OUTPUT_DIR", "data/audio")
        )
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Find piper executable
        self.piper_path = piper_path or self._find_piper()
        self._logger = logging.getLogger(f"{__name__}.AudioGenerator")

        if not self.piper_path:
            self._logger.warning(
                "Piper TTS not found in PATH. Install with: pip install piper-tts"
            )
        else:
            # Ensure voice model is available
            self._ensure_voice_available()

    def _find_piper(self) -> Optional[str]:
        """Find piper executable, checking conda env bin directory."""
        import sys

        # First try shutil.which
        piper_path = shutil.which("piper")
        if piper_path:
            return piper_path

        # Check in the same directory as Python executable (for conda envs)
        python_bin_dir = Path(sys.executable).parent
        conda_piper = python_bin_dir / "piper"
        if conda_piper.exists():
            return str(conda_piper)

        return None

    def _ensure_voice_available(self) -> bool:
        """Ensure the voice model is downloaded and available."""
        try:
            # Check if voice model file exists
            voice_path = PIPER_DATA_DIR / f"{self.voice_model}.onnx"
            if voice_path.exists():
                return True

            self._logger.info(f"Voice model {self.voice_model} not found, downloading...")

            # Try to download the voice
            from piper.download_voices import download_voice
            PIPER_DATA_DIR.mkdir(parents=True, exist_ok=True)
            download_voice(self.voice_model, PIPER_DATA_DIR)
            self._logger.info(f"Voice model {self.voice_model} downloaded successfully")
            return True

        except Exception as e:
            self._logger.warning(f"Failed to ensure voice available: {e}")
            return False

    def _check_piper_available(self) -> bool:
        """Check if Piper TTS is available."""
        if not self.piper_path:
            return False

        try:
            result = subprocess.run(
                [self.piper_path, "--help"],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False

    def _prepare_text_for_speech(self, text: str) -> str:
        """
        Prepare text for text-to-speech conversion.

        Cleans markdown, expands abbreviations, and improves
        text for natural speech synthesis.
        """
        # Remove markdown formatting
        for pattern, replacement in self.MARKDOWN_PATTERNS:
            text = re.sub(pattern, replacement, text, flags=re.MULTILINE)

        # Expand abbreviations
        for abbr, expansion in self.ABBREVIATIONS.items():
            text = text.replace(abbr, expansion)

        # Clean up whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' +', ' ', text)

        # Add pauses for better pacing
        text = text.replace('. ', '.\n')
        text = text.replace('? ', '?\n')
        text = text.replace('! ', '!\n')

        # Remove any remaining special characters
        text = re.sub(r'[*_~`]', '', text)

        return text.strip()

    async def generate(
        self,
        text: str,
        briefing_id: str,
        output_format: str = "wav"
    ) -> Optional[str]:
        """
        Generate audio file from text.

        Args:
            text: Text to convert to speech
            briefing_id: ID for the output file
            output_format: Output format (wav, mp3)

        Returns:
            Path to generated audio file, or None if failed
        """
        if not self._check_piper_available():
            self._logger.error("Piper TTS not available")
            return None

        output_path = self.output_dir / f"{briefing_id}.{output_format}"

        try:
            # Prepare text
            prepared_text = self._prepare_text_for_speech(text)

            if not prepared_text:
                self._logger.warning("No text to convert to speech")
                return None

            self._logger.info(
                f"Generating audio for briefing {briefing_id} "
                f"({len(prepared_text)} chars)"
            )

            # Build piper command with data directory
            model_path = PIPER_DATA_DIR / f"{self.voice_model}.onnx"
            cmd = [
                self.piper_path,
                "--model", str(model_path),
                "--output_file", str(output_path),
                "--data-dir", str(PIPER_DATA_DIR)
            ]

            # Run piper
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await process.communicate(
                input=prepared_text.encode('utf-8')
            )

            if process.returncode != 0:
                error_msg = stderr.decode('utf-8')
                self._logger.error(f"Piper failed: {error_msg}")
                raise AudioGenerationError(f"Piper TTS failed: {error_msg}")

            if output_path.exists():
                file_size = output_path.stat().st_size
                self._logger.info(
                    f"Generated audio file: {output_path} ({file_size} bytes)"
                )
                return str(output_path)
            else:
                self._logger.error("Audio file was not created")
                return None

        except asyncio.TimeoutError:
            self._logger.error("Audio generation timed out")
            return None
        except Exception as e:
            self._logger.error(f"Audio generation failed: {e}")
            return None

    async def generate_from_sections(
        self,
        sections: list,
        briefing_id: str,
        include_intro: bool = True,
    ) -> Optional[str]:
        """
        Generate audio from briefing sections with pacing.

        Args:
            sections: List of section dictionaries or BriefingSection objects
            briefing_id: ID for the output file
            include_intro: Whether to include introduction

        Returns:
            Path to generated audio file
        """
        parts = []

        if include_intro:
            parts.append("Intelligence Briefing.")
            parts.append("Generated by The Pulse.")
            parts.append("")

        for i, section in enumerate(sections, 1):
            # Handle both dict and object
            if hasattr(section, 'title'):
                title = section.title
                summary = section.summary
            else:
                title = section.get('title', f'Section {i}')
                summary = section.get('summary', '')

            parts.append(f"Section {i}. {title}.")
            parts.append("")
            parts.append(summary)
            parts.append("")

        full_text = "\n".join(parts)
        return await self.generate(full_text, briefing_id)

    def get_available_voices(self) -> list:
        """Get list of available Piper voice models."""
        if not self._check_piper_available():
            return []

        # Common voice models
        # In practice, you'd scan the model directory
        common_voices = [
            "en_US-lessac-medium",
            "en_US-lessac-high",
            "en_US-amy-medium",
            "en_US-ryan-medium",
            "en_GB-alan-medium",
            "en_GB-jenny_dioco-medium",
        ]

        return common_voices

    async def estimate_duration(self, text: str) -> float:
        """
        Estimate audio duration in seconds.

        Based on average speaking rate of ~150 words per minute.
        """
        prepared = self._prepare_text_for_speech(text)
        word_count = len(prepared.split())
        words_per_second = 150 / 60
        return word_count / words_per_second

    def delete_audio(self, briefing_id: str) -> bool:
        """Delete audio file for a briefing."""
        for ext in ['wav', 'mp3']:
            path = self.output_dir / f"{briefing_id}.{ext}"
            if path.exists():
                try:
                    path.unlink()
                    self._logger.info(f"Deleted audio file: {path}")
                    return True
                except Exception as e:
                    self._logger.error(f"Failed to delete {path}: {e}")

        return False

    def list_audio_files(self) -> list:
        """List all generated audio files."""
        files = []
        for ext in ['wav', 'mp3']:
            for path in self.output_dir.glob(f"*.{ext}"):
                files.append({
                    "briefing_id": path.stem,
                    "path": str(path),
                    "size": path.stat().st_size,
                    "format": ext,
                })
        return files


class FallbackAudioGenerator:
    """
    Fallback audio generator when Piper is not available.

    Uses espeak as a fallback or logs a warning.
    """

    def __init__(self, output_dir: Optional[str] = None):
        self.output_dir = Path(
            output_dir or os.getenv("AUDIO_OUTPUT_DIR", "data/audio")
        )
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.espeak_path = shutil.which("espeak-ng") or shutil.which("espeak")
        self._logger = logging.getLogger(f"{__name__}.FallbackAudioGenerator")

    async def generate(
        self,
        text: str,
        briefing_id: str,
        output_format: str = "wav"
    ) -> Optional[str]:
        """Generate audio using espeak as fallback."""
        if not self.espeak_path:
            self._logger.warning(
                "No TTS engine available. Install piper-tts or espeak-ng."
            )
            return None

        output_path = self.output_dir / f"{briefing_id}.{output_format}"

        try:
            cmd = [
                self.espeak_path,
                "-w", str(output_path),
                text[:5000]  # Limit text length
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            await process.communicate()

            if output_path.exists():
                return str(output_path)

        except Exception as e:
            self._logger.error(f"Fallback TTS failed: {e}")

        return None
