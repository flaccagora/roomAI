import json
import requests
from ollama import chat
from pydantic import BaseModel

class Output(BaseModel):
        status: str
        motivation: str


class LLMAnalizer():
    def __init__(self, llm):
        # get prompt form file
        with open("backend/prompt.md", "r") as f:
            self.prompt = f.read()
        self.llm = llm

    # def analize_post(self, post):
        
    #     # Send the prompt to local Ollama LLM
    #     response = requests.post(
    #         "http://localhost:11434/api/generate",
    #         json={
    #             "model": self.llm,
    #             "prompt": self.prompt + post["text"],
    #             "stream": False,
    #             "format": {
    #                 "type": "object",
    #                 "properties": {
    #                 "stato": {
    #                     "type": "string"
    #                 },
    #                 "motivo": {
    #                     "type": "string"
    #                 }
    #                 }
    #             }
    #         }
    #     )
    #     analysis = response.json()["response"]

    #     analysis_dict = json.loads(analysis)
    #     print(analysis_dict)

    #     return analysis_dict

    def analize_post(self, post):

        response = chat(
        messages=[
            {'role': 'system', 'content': self.prompt},
            {'role': 'user', 'content': post["text"]}
        ],
        model=self.llm,
        format=Output.model_json_schema(),
        )

        analysis = Output.model_validate_json(response.message.content)
        analysis_dict = json.loads(analysis.model_dump_json())
        print(analysis_dict)

        return analysis_dict


if __name__ == "__main__":
    analizer = LLMAnalizer()
    
    print(analizer.prompt)
