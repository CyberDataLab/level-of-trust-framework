from ollama import Client

ollama = Client(
    host='http://localhost:11434',
)

with open('data/ollamaContext.txt', 'r', encoding='utf-8') as file:
    context = file.read()

prompt = (f"{context} {input("Query: ")}")

response = ollama.chat(model="gemma3:27b-it-q4_K_M", messages=[
            {
                'role': 'user',
                'content': context,
            },
        ])


print(prompt + "\n------------------------------------------------\n")
print(response['message']['content'])
