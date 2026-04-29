from fastapi import FastAPI

app = FastAPI()


@app.get("/orgs/{org_id}/projects/{project_id}")
def get_project(org_id: str, project_id: str):
    return db.projects.find_one({"org_id": org_id, "id": project_id})


class ProjectStore:
    def find_one(self, query):
        return query


class Database:
    projects = ProjectStore()


db = Database()
