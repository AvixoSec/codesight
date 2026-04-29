from flask import Flask, request

app = Flask(__name__)


@app.route("/users")
def users():
    term = request.args["q"]
    query = f"SELECT id, email FROM users WHERE email = '{term}'"
    return db.execute(query).fetchall()


class Result:
    def fetchall(self):
        return []


class Database:
    def execute(self, query):
        return Result()


db = Database()
