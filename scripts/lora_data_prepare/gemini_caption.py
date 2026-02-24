"""Gemini service for audio analysis via the Gemini API.

This module provides a service for interacting with Gemini's API,
supporting audio inputs, file uploads, streaming, and structured outputs.
"""

import os
import base64
import json
import mimetypes
from typing import Optional, List, Dict, Any, Tuple, Union, Generator
from pathlib import Path

import requests

prompt = """Analyze the input audio to generate detailed caption and lyrics. 
lyrics need contain structured tags for chorus, verse, bridge, etc.
**Output Format:**
```json
{
    "caption": <str>,
    "lyrics": "[Intro] <str>, [Verse] <str>..."
}
```
"""


class GeminiService:
    """Service for handling Gemini API audio interactions."""

    SUPPORTED_AUDIO_TYPES = [
        "audio/wav",
        "audio/mp3",
        "audio/aiff",
        "audio/aac",
        "audio/ogg",
        "audio/flac",
    ]

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://generativelanguage.googleapis.com",
        model_name: str = "gemini-3-flash",
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name

    def _get_endpoint(
        self, endpoint_type: str = "generate", model_name: Optional[str] = None
    ) -> str:
        model = model_name or self.model_name

        if endpoint_type == "generate":
            return f"{self.base_url}/v1beta/models/{model}:generateContent"
        elif endpoint_type == "stream":
            return (
                f"{self.base_url}/v1beta/models/{model}:streamGenerateContent?alt=sse"
            )
        elif endpoint_type == "upload":
            return f"{self.base_url}/upload/v1beta/files"
        elif endpoint_type == "files":
            return f"{self.base_url}/v1beta/files"
        else:
            raise ValueError(f"Unknown endpoint type: {endpoint_type}")

    def _get_headers(self) -> Dict[str, str]:
        return {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}

    def _encode_file_to_base64(self, file_path: str) -> str:
        with open(file_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def _get_mime_type(self, file_path: str) -> str:
        mime_type, _ = mimetypes.guess_type(file_path)
        if not mime_type:
            ext = Path(file_path).suffix.lower()
            mime_map = {
                ".mp3": "audio/mp3",
                ".wav": "audio/wav",
                ".aac": "audio/aac",
                ".ogg": "audio/ogg",
                ".flac": "audio/flac",
                ".aiff": "audio/aiff",
            }
            mime_type = mime_map.get(ext, "application/octet-stream")
        return mime_type

    def upload_file(
        self,
        file_path: str,
        display_name: Optional[str] = None,
        mime_type: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Upload a file using the Files API.

        Use this for files larger than 20MB or when you want to reuse files
        across multiple requests.
        """
        try:
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File not found: {file_path}")

            if mime_type is None:
                mime_type = self._get_mime_type(file_path)

            num_bytes = os.path.getsize(file_path)

            if display_name is None:
                display_name = Path(file_path).stem

            init_headers = {
                "x-goog-api-key": self.api_key,
                "X-Goog-Upload-Protocol": "resumable",
                "X-Goog-Upload-Command": "start",
                "X-Goog-Upload-Header-Content-Length": str(num_bytes),
                "X-Goog-Upload-Header-Content-Type": mime_type,
                "Content-Type": "application/json",
            }

            init_data = {"file": {"display_name": display_name}}

            upload_endpoint = self._get_endpoint("upload")
            response = requests.post(
                upload_endpoint, headers=init_headers, json=init_data
            )

            if response.status_code != 200:
                print(
                    f"Failed to initiate upload: {response.status_code} - {response.text}"
                )
                return None

            upload_url = response.headers.get("x-goog-upload-url")
            if not upload_url:
                print("No upload URL in response headers")
                return None

            with open(file_path, "rb") as f:
                file_data = f.read()

            upload_headers = {
                "Content-Length": str(num_bytes),
                "X-Goog-Upload-Offset": "0",
                "X-Goog-Upload-Command": "upload, finalize",
            }

            response = requests.post(upload_url, headers=upload_headers, data=file_data)

            if response.status_code == 200:
                file_info = response.json()
                print(
                    f"File uploaded successfully: {file_info.get('file', {}).get('uri')}"
                )
                return file_info.get("file")
            else:
                print(
                    f"Failed to upload file data: {response.status_code} - {response.text}"
                )
                return None

        except Exception as e:
            print(f"Error uploading file: {e}")
            return None

    def get_file_info(self, file_name: str) -> Optional[Dict[str, Any]]:
        try:
            files_endpoint = self._get_endpoint("files")
            url = f"{files_endpoint}/{file_name}"
            response = requests.get(url, headers=self._get_headers())

            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"Error getting file info: {e}")
            return None

    def delete_file(self, file_name: str) -> bool:
        try:
            files_endpoint = self._get_endpoint("files")
            url = f"{files_endpoint}/{file_name}"
            response = requests.delete(url, headers=self._get_headers())
            return response.status_code == 204
        except Exception as e:
            print(f"Error deleting file: {e}")
            return False

    def generate_content(
        self,
        prompt: Union[str, List[Dict[str, Any]]],
        audio: Optional[List[str]] = None,
        file_uris: Optional[List[Dict[str, str]]] = None,
        system_instruction: Optional[str] = None,
        generation_config: Optional[Dict[str, Any]] = None,
        history: Optional[List[Dict[str, Any]]] = None,
        model_name: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Generate content with audio support.

        Args:
            prompt: Text prompt or list of content parts
            audio: List of audio file paths (for inline data)
            file_uris: List of file URIs from uploaded files, each dict with 'mime_type' and 'file_uri'
            system_instruction: Optional system instruction to guide behavior
            generation_config: Optional generation configuration (temperature, topP, etc.)
            history: Optional conversation history for multi-turn chat
            model_name: Optional model name to use for this request (overrides default)
        """
        try:
            body = self._build_request_body(
                prompt=prompt,
                audio=audio,
                file_uris=file_uris,
                system_instruction=system_instruction,
                generation_config=generation_config,
                history=history,
            )

            endpoint = self._get_endpoint("generate", model_name)
            response = requests.post(
                endpoint, headers=self._get_headers(), json=body, timeout=300
            )

            if response.status_code == 200:
                return response.json()
            else:
                print(
                    f"API call failed: {response.status_code} - {response.text[:500]}"
                )
                return None

        except Exception as e:
            print(f"Error generating content: {e}")
            return None

    def stream_generate_content(
        self,
        prompt: Union[str, List[Dict[str, Any]]],
        audio: Optional[List[str]] = None,
        file_uris: Optional[List[Dict[str, str]]] = None,
        system_instruction: Optional[str] = None,
        generation_config: Optional[Dict[str, Any]] = None,
        history: Optional[List[Dict[str, Any]]] = None,
        model_name: Optional[str] = None,
    ) -> Generator[Dict[str, Any], None, None]:
        """Stream generate content with server-sent events."""
        try:
            body = self._build_request_body(
                prompt=prompt,
                audio=audio,
                file_uris=file_uris,
                system_instruction=system_instruction,
                generation_config=generation_config,
                history=history,
            )

            endpoint = self._get_endpoint("stream", model_name)
            response = requests.post(
                endpoint,
                headers=self._get_headers(),
                json=body,
                stream=True,
                timeout=300,
            )

            if response.status_code == 200:
                for line in response.iter_lines():
                    if line:
                        line = line.decode("utf-8")
                        if line.startswith("data: "):
                            data = line[6:]
                            try:
                                yield json.loads(data)
                            except json.JSONDecodeError:
                                continue
            else:
                print(
                    f"Streaming failed: {response.status_code} - {response.text[:500]}"
                )

        except Exception as e:
            print(f"Error streaming content: {e}")

    def _build_request_body(
        self,
        prompt: Union[str, List[Dict[str, Any]]],
        audio: Optional[List[str]] = None,
        file_uris: Optional[List[Dict[str, str]]] = None,
        system_instruction: Optional[str] = None,
        generation_config: Optional[Dict[str, Any]] = None,
        history: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        body = {}

        if system_instruction:
            body["system_instruction"] = {"parts": [{"text": system_instruction}]}

        contents = []

        if history:
            contents.extend(history)

        parts = []

        if isinstance(prompt, str):
            parts.append({"text": prompt})
        elif isinstance(prompt, list):
            parts.extend(prompt)

        if audio:
            for audio_path in audio:
                mime_type = self._get_mime_type(audio_path)
                audio_data = self._encode_file_to_base64(audio_path)
                parts.append(
                    {"inline_data": {"mime_type": mime_type, "data": audio_data}}
                )

        if file_uris:
            for file_ref in file_uris:
                parts.append(
                    {
                        "file_data": {
                            "mime_type": file_ref.get("mime_type"),
                            "file_uri": file_ref.get("file_uri"),
                        }
                    }
                )

        contents.append({"role": "user", "parts": parts})

        body["contents"] = contents

        if generation_config:
            body["generationConfig"] = generation_config

        return body

    def extract_text(self, response: Dict[str, Any]) -> Optional[str]:
        try:
            if response.get("candidates"):
                candidate = response["candidates"][0]
                if candidate.get("content", {}).get("parts"):
                    parts = candidate["content"]["parts"]
                    texts = [part.get("text", "") for part in parts if "text" in part]
                    return " ".join(texts)
        except Exception as e:
            print(f"Error extracting text: {e}")
        return None

    def analyze_audio(
        self,
        audio_path: str,
        prompt: str,
        model_name: Optional[str] = "gemini-3-pro-preview",
        use_upload: bool = False,
        **kwargs,
    ) -> Optional[str]:
        """Analyze audio with a text prompt.

        Args:
            audio_path: Path to the audio file
            prompt: Text prompt for analysis
            model_name: Model name for analysis
            use_upload: Whether to use File API (recommended for audio > 20MB)
        """
        generation_config = {
            "thinkingConfig": {
                "thinkingLevel": "HIGH",
            },
            "responseMimeType": "application/json",
        }
        if use_upload:
            file_info = self.upload_file(audio_path)
            if file_info:
                file_uris = [
                    {
                        "mime_type": file_info.get("mimeType"),
                        "file_uri": file_info.get("uri"),
                    }
                ]
                response = self.generate_content(
                    prompt=prompt,
                    file_uris=file_uris,
                    model_name=model_name,
                    generation_config=generation_config,
                    **kwargs,
                )
                if response is None:
                    return None
                data = self.extract_text(response)
                if data is None:
                    return None
                result = data.replace("```json", "").replace("```", "")
                return result
            return None
        else:
            response = self.generate_content(
                prompt=prompt,
                audio=[audio_path],
                model_name=model_name,
                generation_config=generation_config,
                **kwargs,
            )
            if response is None:
                return None
            data = self.extract_text(response)
            if data is None:
                return None
            result = data.replace("```json", "").replace("```", "")
            return result

    def transcribe_audio(
        self,
        audio_path: str,
        use_upload: bool = False,
        model_name: Optional[str] = "gemini-3-pro-preview",
        **kwargs,
    ) -> Optional[str]:
        """Transcribe audio to text."""
        response = self.analyze_audio(
            audio_path=audio_path,
            prompt="Please provide a complete transcription of this audio.",
            use_upload=use_upload,
            model_name=model_name,
            **kwargs,
        )
        return self.extract_text(response) if response else None


_gemini_service = None


def get_gemini_service(
    api_key: Optional[str] = None,
    base_url: str = "https://generativelanguage.googleapis.com",
    model_name: str = "gemini-3-flash",
) -> GeminiService:
    global _gemini_service

    if not api_key:
        raise ValueError(
            "API key must be provided or set in GEMINI_API_KEY environment variable"
        )

    if _gemini_service is None:
        _gemini_service = GeminiService(api_key, base_url, model_name)

    return _gemini_service


AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".ogg", ".aac", ".aiff"}


def extract_json_from_text(text: str):
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return None
    return text[start: end + 1]


def analysis_audio_by_gemini(
    api_key: str, base_url: str, audio_path: str, duration=None, max_retry: int = 3
):
    global _gemini_service
    if _gemini_service is None:
        _gemini_service = get_gemini_service(api_key, base_url)

    result = _gemini_service.analyze_audio(
        audio_path, prompt, model_name="gemini-3-pro-preview"
    )
    try:
        json_result = json.loads(result)
    except:
        json_result = extract_json_from_text(result)
    if json_result is None:
        raise Exception(f"无法解析json, {result}")
    return json_result


def analysis_audio_to_files(
    api_key: str,
    base_url: str,
    audio_path: str,
    output_dir: str,
):
    """Analyze audio and save lyrics and caption as separate txt files.

    Output files:
        {stem}.lyrics.txt  - lyrics
        {stem}.caption.txt - caption

    Args:
        api_key: Gemini API key
        base_url: Gemini API base URL
        audio_path: Path to the audio file
        output_dir: Directory to save output txt files
    """
    json_result = analysis_audio_by_gemini(api_key, base_url, audio_path)

    if isinstance(json_result, str):
        json_result = json.loads(json_result)

    stem = Path(audio_path).stem
    os.makedirs(output_dir, exist_ok=True)

    lyrics = json_result.get("lyrics", "")
    caption = json_result.get("caption", "")

    lyrics_path = os.path.join(output_dir, f"{stem}.lyrics.txt")
    with open(lyrics_path, "w", encoding="utf-8") as f:
        f.write(lyrics)

    caption_path = os.path.join(output_dir, f"{stem}.caption.txt")
    with open(caption_path, "w", encoding="utf-8") as f:
        f.write(caption)

    return lyrics_path, caption_path


def process_folder(
    input_dir: str,
    output_dir: str,
    api_key: str,
    base_url: str = "https://generativelanguage.googleapis.com",
) -> List[str]:
    """Analyze all audio files in a folder, saving lyrics and caption txt files.

    Args:
        input_dir: Directory containing audio files
        output_dir: Directory to save output txt files
        api_key: Gemini API key
        base_url: Gemini API base URL

    Returns:
        List of output file paths
    """
    input_path = Path(input_dir)
    if not input_path.is_dir():
        raise NotADirectoryError(f"Input directory not found: {input_dir}")

    os.makedirs(output_dir, exist_ok=True)

    audio_files = sorted(
        f for f in input_path.iterdir()
        if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS
    )

    if not audio_files:
        print(f"No audio files found in {input_dir}")
        return []

    output_paths = []
    for i, audio_file in enumerate(audio_files, 1):
        print(f"[{i}/{len(audio_files)}] {audio_file.name}")

        try:
            lyrics_path, caption_path = analysis_audio_to_files(
                api_key=api_key,
                base_url=base_url,
                audio_path=str(audio_file),
                output_dir=output_dir,
            )
            output_paths.extend([lyrics_path, caption_path])
            print(f"  -> {Path(lyrics_path).name}, {Path(caption_path).name}")
        except Exception as e:
            print(f"  Error: {e}")

    print(f"Done: {len(output_paths) // 2}/{len(audio_files)} files processed")
    return output_paths
