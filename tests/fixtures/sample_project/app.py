from flask import request


def search_users(db):
    term = request.args["q"]
    sql = f"SELECT * FROM users WHERE name = '{term}'"
    return db.execute(sql)
