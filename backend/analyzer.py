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

    def analize_post(self, post):

        try:
            post_text = post["text"]
        except KeyError:
            post_text = post["message"]

        response = chat(
        messages=[
            {'role': 'system', 'content': self.prompt},
            {'role': 'user', 'content': post_text}
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
