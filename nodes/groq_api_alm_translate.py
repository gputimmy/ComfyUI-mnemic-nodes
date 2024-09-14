# nodes/groq_api_alm_translate.py
import os
import json
import time
from configparser import ConfigParser
from colorama import init, Fore, Style
from groq import Groq
import requests

from ..utils.api_utils import load_prompt_options, get_prompt_content

init()  # Initialize colorama

class GroqAPIALMTranslate:
    DEFAULT_PROMPT = "Translate the audio file using the style and guidance of [user_input]"

    # Only whisper-large-v3 supports translation
    TRANSLATION_MODELS = [
        "whisper-large-v3",
    ]

    SUPPORTED_AUDIO_FORMATS = ['mp3', 'mp4', 'mpeg', 'mpga', 'm4a', 'wav', 'webm']

    CLASS_TYPE = "text"  # Added CLASS_TYPE property

    def __init__(self):
        current_directory = os.path.dirname(os.path.realpath(__file__))
        groq_directory = os.path.join(current_directory, 'groq')
        config_path = os.path.join(groq_directory, 'GroqConfig.ini')
        self.config = ConfigParser()
        self.config.read(config_path)
        self.api_key = self.config.get('API', 'key')
        self.client = Groq(api_key=self.api_key)

        # Load prompt options
        prompt_files = [
            os.path.join(groq_directory, 'DefaultPrompts_ALM_Translate.json'),
            os.path.join(groq_directory, 'UserPrompts_ALM_Translate.json')
        ]
        self.prompt_options = load_prompt_options(prompt_files)

    @classmethod
    def INPUT_TYPES(cls):
        try:
            current_directory = os.path.dirname(os.path.realpath(__file__))
            groq_directory = os.path.join(current_directory, 'groq')
            prompt_files = [
                os.path.join(groq_directory, 'DefaultPrompts_ALM_Translate.json'),
                os.path.join(groq_directory, 'UserPrompts_ALM_Translate.json')
            ]
            prompt_options = load_prompt_options(prompt_files)
        except Exception as e:
            print(Fore.RED + f"Failed to load prompt options: {e}" + Style.RESET_ALL)
            prompt_options = {}

        return {
            "required": {
                "model": (cls.TRANSLATION_MODELS, {"tooltip": "Select the translation model to use."}),
                "file_path": ("STRING", {"label": "Audio file path", "multiline": False, "default": "", "tooltip": "Path to the audio file for translation."}),
                "preset": ([cls.DEFAULT_PROMPT] + list(prompt_options.keys()), {"tooltip": "Select a preset or custom prompt for guiding the translation."}),
                "user_input": ("STRING", {"label": "User Input (for prompt)", "multiline": True, "default": "", "tooltip": "Optional user input to guide the translation process."}),
                "response_format": (["json", "verbose_json", "text", "text_with_timestamps", "text_with_linebreaks"], {"tooltip": "Choose the format in which the translation output will be returned."}),
                "temperature": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.1, "tooltip": "Controls randomness in responses.\n\nA higher temperature makes the model take more risks, leading to more creative or varied answers.\n\nA lower temperature (closer to 0.1) makes the model more focused and predictable."}),
                "max_retries": ("INT", {"default": 2, "min": 1, "max": 10, "step": 1, "tooltip": "Maximum number of retries in case of failures."}),
            }
        }

    RETURN_TYPES = ("STRING", "BOOLEAN", "STRING")
    RETURN_NAMES = ("translation_result", "success", "status_code")
    OUTPUT_TOOLTIPS = ("The API response. This is the translation generated by the model", "Whether the request was successful", "The status code of the request")
    FUNCTION = "process_translation_request"
    CATEGORY = "⚡ MNeMiC Nodes"
    DESCRIPTION = "Uses Groq API to translate audio."
    OUTPUT_NODE = True

    def process_translation_request(self, model, file_path, preset, user_input, response_format, temperature, max_retries):
        # Validate file path
        if not os.path.isfile(file_path):
            print(Fore.RED + f"Error: File not found at path {file_path}" + Style.RESET_ALL)
            return "File not found.", False, "400 Bad Request"

        # Validate file extension
        file_extension = file_path.split('.')[-1].lower()
        if file_extension not in self.SUPPORTED_AUDIO_FORMATS:
            print(Fore.RED + f"Error: Unsupported audio format '{file_extension}'. Supported formats are: {', '.join(self.SUPPORTED_AUDIO_FORMATS)}" + Style.RESET_ALL)
            return f"Unsupported audio format '{file_extension}'.", False, "400 Bad Request"

        # Load the audio file
        try:
            with open(file_path, 'rb') as audio_file:
                audio_data = audio_file.read()
        except Exception as e:
            print(Fore.RED + f"Error reading audio file: {str(e)}" + Style.RESET_ALL)
            return "Error reading audio file.", False, "400 Bad Request"

        # Prepare the prompt
        if preset == self.DEFAULT_PROMPT:
            prompt = self.DEFAULT_PROMPT.replace('[user_input]', user_input.strip()) if user_input else None
        else:
            prompt_template = get_prompt_content(self.prompt_options, preset)
            prompt = prompt_template.replace('[user_input]', user_input.strip())

        # Limit the prompt to 224 tokens
        # if prompt:
        #     prompt = prompt[:1000]

        # Adjust api_response_format based on response_format
        if response_format in ['json', 'verbose_json', 'text']:
            api_response_format = response_format
        elif response_format in ['text_with_timestamps', 'text_with_linebreaks']:
            api_response_format = 'verbose_json'
        else:
            return "Unknown response format.", False, "400 Bad Request"

        url = 'https://api.groq.com/openai/v1/audio/translations'
        headers = {'Authorization': f'Bearer {self.api_key}'}
        files = {'file': (os.path.basename(file_path), audio_data)}
        data = {
            'model': model,
            'response_format': api_response_format,
            'temperature': str(temperature),
        }
        if prompt:
            data['prompt'] = prompt

        print(f"Sending request to {url} with data: {data} and headers: {headers}")

        # Send the request
        for attempt in range(max_retries):
            try:
                response = requests.post(url, headers=headers, data=data, files=files)
                print(f"Response status: {response.status_code}")
                if response.status_code == 200:
                    if api_response_format == "text":
                        if response_format == "text":
                            # Return plain text as is
                            return response.text, True, "200 OK"
                    elif api_response_format in ["json", "verbose_json"]:
                        try:
                            response_json = json.loads(response.text)
                        except Exception as e:
                            print(Fore.RED + f"Error parsing JSON response: {str(e)}" + Style.RESET_ALL)
                            return "Error parsing JSON response.", False, "200 OK but failed to parse JSON"
                        if response_format == "json":
                            # Return JSON as formatted string
                            return json.dumps(response_json, indent=4), True, "200 OK"
                        elif response_format == "verbose_json":
                            # Return verbose JSON as formatted string
                            return json.dumps(response_json, indent=4), True, "200 OK"
                        elif response_format == "text_with_timestamps":
                            # Process segments to produce line-based timestamps
                            segments = response_json.get('segments', [])
                            translation_text = ""
                            for segment in segments:
                                start_time = segment.get('start', 0)
                                # Convert start_time to minutes:seconds.milliseconds
                                minutes = int(start_time // 60)
                                seconds = int(start_time % 60)
                                milliseconds = int((start_time - int(start_time)) * 1000)
                                timestamp = f"[{minutes:02d}:{seconds:02d}.{milliseconds:03d}]"
                                text = segment.get('text', '').strip()
                                translation_text += f"{timestamp}{text}\n"
                            return translation_text.strip(), True, "200 OK"
                        elif response_format == "text_with_linebreaks":
                            # Extract text from each segment and concatenate with line breaks
                            segments = response_json.get('segments', [])
                            translation_text = ""
                            for segment in segments:
                                text = segment.get('text', '').strip()
                                translation_text += f"{text}\n"
                            return translation_text.strip(), True, "200 OK"
                    else:
                        return "Unknown api_response_format.", False, "400 Bad Request"
                else:
                    print(Fore.RED + f"Error: {response.status_code} {response.reason}" + Style.RESET_ALL)
                    return response.text, False, f"{response.status_code} {response.reason}"
            except Exception as e:
                print(Fore.RED + f"Request failed: {str(e)}" + Style.RESET_ALL)
                time.sleep(2)
        return "Failed after all retries.", False, "Failed after all retries"