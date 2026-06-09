
from storage.database import Database


db = Database()

docs = db.get_all_documents()

print(len(docs))