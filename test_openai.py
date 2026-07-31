from dotenv import load_dotenv
from openai import OpenAI

# Load variables from .env
load_dotenv()

# Create OpenAI client
client = OpenAI()

# Send a request
response = client.responses.create(
    model="gpt-5.5",
    input="Say hello to Arshad and explain what RAG is in one sentence."
)

print(response.output_text)