import os
import google.generativeai as genai
from dotenv import load_dotenv

# Load .env
load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    print("No GEMINI_API_KEY found in .env")
    exit(1)

print(f"Checking models for key: {api_key[:10]}...")

try:
    genai.configure(api_key=api_key)
    print("\nAvailable Models:")
    print("-" * 30)
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(f"- {m.name}")
    print("-" * 30)
except Exception as e:
    print(f"\nError: {e}")
