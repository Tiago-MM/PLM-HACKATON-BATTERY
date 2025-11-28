from mistralai import Mistral
import os


client = Mistral(api_key="15lJc7S6zEs9u4HNVeCLiuMC7bXUTMhk")
inputs = [
    {"role": "user", "content": "Hello!"}
]

completion_args = {
    "temperature": 0.7,
    "max_tokens": 2048,
    "top_p": 1
}

tools = []

response = client.beta.conversations.start(
    inputs=inputs,
    model="mistral-medium-latest",
    instructions=""" tu es un assistant IA spécialisé dans la gestion des batteries pour véhicules électriques.
    Tu aides les utilisateurs à trouver des informations sur les batteries, les constructeurs, et les statistiques associées.
    Sois précis et concis dans tes réponses.""",
    completion_args=completion_args,
    tools=tools,
)

print(response.outputs[0].content)
