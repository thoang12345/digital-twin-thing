from typing import Dict, List


class ChatMemory:
    def __init__(self,max_messages:int=20):
        self.max_messages=max_messages
        self.messages: List[Dict[str,str]]=[]
    
    def add_user_message(self, content:str)->None:
        self.messages.append({
            "role":"user",
            "content": content,
        })
        self._trim()

    def add_assistant_message(self, content:str)->None:
        self.messages.append({
            "role":"assistant",
            "content": content,
        })
        self._trim()

    def get_messages(self)->List[Dict[str,str]]:
        return list(self.messages)
    
    def clear(self)->None:
        self.messages.clear()

    def _trim(self)-> None:
        if len(self.messages) > self.max_messages:
            self.messages=self.messages[-self.max_messages:]
