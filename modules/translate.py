import json
from typing import Dict, Any, List
import os
from mistralai import Mistral
from dotenv import load_dotenv
from tqdm import tqdm
import spacy
import time

load_dotenv(override=True)
nlp = spacy.load("it_core_news_sm")

def extract_sentences(text: str) -> List[str]:
    doc = nlp(text)
    return [sent.text.strip() for sent in doc.sents if sent.text.strip()]

def load_json_content(file_path: str) -> Dict[str, Any]:
    with open(file_path, 'r', encoding='utf-8') as file:
        return json.load(file)

def should_split_text(text: str, api_key: str) -> bool:
    truncated_text = text if len(text) <= 2000 else text[:2000] + "... (truncated)"
    model = "mistral-small-latest"
    client = Mistral(api_key=api_key)

    prompt = f"""
    Analyze the following text and determine if it is regular content that should be split into sentences for translation, or if it is something else like an index, table of contents, bibliography, etc., that should be treated as a whole.

    Text:
    {truncated_text}

    Respond with 'split' if the text should be split into sentences, or 'whole' if it should be treated as a whole.
    """

    chat_response = client.chat.complete(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "You are a text analysis assistant. Determine if the given text should be split into sentences for translation or treated as a whole. Respond with 'split' or 'whole'."
            },
            {
                "role": "user",
                "content": prompt,
            },
        ]
    )

    response = chat_response.choices[0].message.content.strip().lower()
    return response == "split"

def translate_text(text: str, api_key: str) -> str:
    model = "mistral-small-latest"
    client = Mistral(api_key=api_key)

    chat_response = client.chat.complete(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "Your task is to translate Italian into English. Keep the format of the text. Return nothing but an accurate translation. Only return the English translation! If there are any other languages other than Italian, translate them to English, too."
            },
            {
                "role": "user",
                "content": f"Translate this from Italian to English: {text}",
            },
        ]
    )

    return chat_response.choices[0].message.content

def process_and_translate(json_file_path: str, translated_json_file_path: str, api_key: str) -> None:
    json_content = load_json_content(json_file_path)

    if os.path.exists(translated_json_file_path):
        with open(translated_json_file_path, 'r', encoding='utf-8') as file:
            output_data = json.load(file)
    else:
        output_data = {"sentences": [], "progress": {"last_processed_page": -1}}

    last_processed_page = output_data["progress"]["last_processed_page"]
    start_page = last_processed_page + 1
    pages = json_content["pages"]

    if start_page >= len(pages):
        print("All pages have already been processed.")
        return

    for page_index in tqdm(range(start_page, len(pages)), desc="Processing pages", initial=start_page, total=len(pages)):
        page = pages[page_index]
        page_text = page["markdown"]

        if not page_text.strip():
            output_data["progress"]["last_processed_page"] = page_index
            with open(translated_json_file_path, 'w', encoding='utf-8') as file:
                json.dump(output_data, file, ensure_ascii=False, indent=4)
            continue

        split_text = should_split_text(page_text, api_key)

        try:
            if split_text:
                sentences = extract_sentences(page_text)
                for sentence in sentences:
                    translated_sentence = translate_text(sentence, api_key)
                    output_data["sentences"].append({
                        "original": sentence,
                        "translated": translated_sentence,
                        "content_type": "split"
                    })
            else:
                translated_text = translate_text(page_text, api_key)
                output_data["sentences"].append({
                    "original": page_text,
                    "translated": translated_text,
                    "content_type": "whole"
                })

            output_data["progress"]["last_processed_page"] = page_index
            with open(translated_json_file_path, 'w', encoding='utf-8') as file:
                json.dump(output_data, file, ensure_ascii=False, indent=4)

        except Exception as e:
            print(f"Error processing page {page_index + 1}: {str(e)}")
            output_data["progress"]["last_processed_page"] = page_index - 1
            with open(translated_json_file_path, 'w', encoding='utf-8') as file:
                json.dump(output_data, file, ensure_ascii=False, indent=4)
            raise

if __name__ == "__main__":
    original_dir = "original/json"
    translated_dir = "translated/json"
    os.makedirs(translated_dir, exist_ok=True)

    json_file_path = os.path.join(original_dir, 'ocr_response.json')
    translated_json_file_path = os.path.join(translated_dir, 'translated_sentences.json')

    api_key = os.getenv("MISTRAL_API_KEY")
    if api_key is None:
        print("MISTRAL_API_KEY not found in the local .env file.")
        exit(1)

    process_and_translate(json_file_path, translated_json_file_path, api_key)
    print(f"Translation process completed. Results saved to {translated_json_file_path}")
