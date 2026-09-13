import base64
import io
from pathlib import Path
from typing import Optional, Callable, Tuple
from PIL import Image

try:
    from mistralai import Mistral
except ImportError:
    from mistralai.client import Mistral

from core.config import MISTRAL_API_KEY, is_internet_available

PIXTRAL_MODEL = "pixtral-12b-2409"


class VisionService:
    """Multimodal image analysis and visual reasoning service powered by Mistral Pixtral."""

    def __init__(self, api_key: str = MISTRAL_API_KEY):
        self.api_key = api_key
        self.client = None
        if self.api_key:
            try:
                self.client = Mistral(api_key=self.api_key)
            except Exception as e:
                print(f"VisionService Mistral client init warning: {e}")
                self.client = None

    @staticmethod
    def encode_image_to_base64(image_input) -> Tuple[str, str]:
        """
        Converts a file path or PIL Image to a Base64 encoded string and detects MIME type.
        Returns: (base64_string, mime_type)
        """
        if isinstance(image_input, (str, Path)):
            path = Path(image_input)
            ext = path.suffix.lower()
            if ext in [".png"]:
                mime_type = "image/png"
            elif ext in [".webp"]:
                mime_type = "image/webp"
            else:
                mime_type = "image/jpeg"

            with open(path, "rb") as f:
                b64_str = base64.b64encode(f.read()).decode("utf-8")
            return b64_str, mime_type

        elif isinstance(image_input, Image.Image):
            buffered = io.BytesIO()
            img_format = getattr(image_input, "format", None)
            if img_format == "PNG":
                mime_type = "image/png"
                image_input.save(buffered, format="PNG")
            else:
                mime_type = "image/jpeg"
                if image_input.mode in ("RGBA", "P"):
                    rgb_img = image_input.convert("RGB")
                    rgb_img.save(buffered, format="JPEG", quality=92)
                else:
                    image_input.save(buffered, format="JPEG", quality=92)

            b64_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
            return b64_str, mime_type

        else:
            raise ValueError(f"Unsupported image input type: {type(image_input)}")

    def analyze_image_stream(
        self,
        image_input,
        prompt: str,
        token_callback: Callable[[str], None],
        status_callback: Optional[Callable[[str], None]] = None,
        stop_check: Optional[Callable[[], bool]] = None,
        search_context: Optional[str] = None
    ) -> str:
        """
        Streams multimodal image analysis using Mistral Pixtral (pixtral-12b-2409).
        Payload format per requirements:
        {"type": "image_url", "image_url": "data:image/jpeg;base64,{base64_string}"}
        """
        if not is_internet_available():
            msg = "⚠️ Network offline: Cannot connect to Mistral Vision AI service."
            token_callback(msg)
            return msg

        if not self.api_key:
            msg = "⚠️ **MISTRAL_API_KEY** not found in `.env`. Please provide an API key to enable image analysis."
            token_callback(msg)
            return msg

        if not self.client:
            try:
                self.client = Mistral(api_key=self.api_key)
            except Exception as e:
                msg = f"❌ Failed to initialize Mistral client: {e}"
                token_callback(msg)
                return msg

        if status_callback:
            status_callback("🖼️ Processing image for Pixtral analysis...")

        try:
            b64_str, mime_type = self.encode_image_to_base64(image_input)
            data_url = f"data:{mime_type};base64,{b64_str}"

            system_instruction = (
                "You are Search Studio's AI Vision & Multimodal Reasoning Assistant.\n"
                "Your objective is to analyze the provided image with high accuracy, solve questions/problems, and provide comprehensive answers:\n\n"
                "1. Direct Answering & Problem Solving:\n"
                "   - If the image contains a question, exam problem, algorithm or coding query, math equation, quiz, or technical concept:\n"
                "     * Identify the question/problem.\n"
                "     * Provide the direct, complete, and accurate answer, solution, derivation, or code immediately.\n"
                "     * Do NOT merely describe what the image looks like or state that you cannot answer—directly answer and solve the problem using your knowledge and any provided search context.\n\n"
                "2. User Instructions & Queries:\n"
                "   - If the user provided a specific question or prompt alongside the image, answer it thoroughly by combining the visual information, extracted text, and search context.\n\n"
                "3. Diagrams, Charts & Documents:\n"
                "   - If the image is a flowchart, architecture diagram, graph, or scanned document, explain the data, workflows, components, and key takeaways clearly.\n\n"
                "4. Photos & Visual Scenes:\n"
                "   - If the image is a photograph, artwork, or scene without text or questions, describe its subjects, context, and visual attributes.\n\n"
                "5. Formatting:\n"
                "   - Use clean Markdown with bold headings, bullet points, and code blocks."
            )

            prompt_clean = prompt.strip() if prompt else ""
            default_prompts = [
                "analyze and describe this photo in detail.",
                "analyze this photo",
                "describe this image"
            ]

            user_text_parts = [system_instruction]

            if prompt_clean and prompt_clean.lower() not in default_prompts:
                user_text_parts.append(f"User Request / Question: {prompt_clean}")
            else:
                user_text_parts.append("Please analyze the image, solve/answer any question or problem contained in it, and provide the complete solution.")

            if search_context and search_context.strip():
                user_text_parts.append(f"=== RELEVANT KNOWLEDGE & SEARCH CONTEXT ===\n{search_context.strip()}")

            full_prompt = "\n\n".join(user_text_parts)

            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": full_prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": data_url
                        }
                    ]
                }
            ]

            if status_callback:
                status_callback("⚡ Analyzing image with Pixtral (pixtral-12b-2409)...")

            full_response = []
            
            # Use official Mistral SDK stream
            try:
                stream_response = self.client.chat.stream(
                    model=PIXTRAL_MODEL,
                    messages=messages
                )

                for chunk in stream_response:
                    if stop_check and stop_check():
                        token_callback("\n\n*[Generation stopped by user]*")
                        break

                    data_obj = getattr(chunk, "data", chunk)
                    choices = getattr(data_obj, "choices", None)
                    if choices and len(choices) > 0:
                        delta = getattr(choices[0], "delta", None)
                        if delta:
                            content = getattr(delta, "content", "")
                            if isinstance(content, str) and content:
                                full_response.append(content)
                                token_callback(content)
                            elif isinstance(content, list):
                                for item in content:
                                    t = getattr(item, "text", str(item))
                                    if t:
                                        full_response.append(t)
                                        token_callback(t)

            except Exception as stream_err:
                # Fallback to standard completion if streaming encounters SDK variance
                if status_callback:
                    status_callback("⚡ Completing Pixtral image query...")
                res = self.client.chat.complete(
                    model=PIXTRAL_MODEL,
                    messages=messages
                )
                if res and res.choices:
                    final_content = res.choices[0].message.content
                    if isinstance(final_content, str):
                        full_response.append(final_content)
                        token_callback(final_content)
                    elif isinstance(final_content, list):
                        for item in final_content:
                            t = getattr(item, "text", str(item))
                            full_response.append(t)
                            token_callback(t)

            final_text = "".join(full_response).strip()
            return final_text

        except Exception as e:
            err_str = str(e)
            user_err_msg = f"❌ **Pixtral Image Analysis Error:** {err_str}"
            token_callback(user_err_msg)
            return user_err_msg
