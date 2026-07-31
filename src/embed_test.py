from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI()

text = """
The Employee will return the company car to CACI in good condition.
"""

response = client.embeddings.create(
    model="text-embedding-3-small",
    input=text
)

embedding = response.data[0].embedding

print(f"Embedding length: {len(embedding)}")

print()

print("First 10 numbers:")

print(embedding[:10])