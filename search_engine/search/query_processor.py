# search/query_processor.py

from indexing.tokenizer import TextPreprocessor


class QueryProcessor:

    def __init__(self):
        self.preprocessor = TextPreprocessor()

    def process(self, query: str) -> list[str]:
        return self.preprocessor.process(query)