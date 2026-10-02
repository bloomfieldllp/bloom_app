with open("routes/sync.py", "r") as f:
    content = f.read()

old_pull = """    if since_dt:
        school_query["updated_at"] = {"$gt": since_dt}
        project_query["updated_at"] = {"$gt": since_dt}
        student_query["updated_at"] = {"$gt": since_dt}"""

new_pull = """    if since_dt:
        school_query["updated_at"] = {"$gt": since_dt}
        project_query["updated_at"] = {"$gt": since_dt}
        
        # If a project was updated recently (e.g. operator assignment changed),
        # we MUST pull all its students regardless of when the student was updated.
        recently_updated_projects = list(db.projects.find({
            "_id": {"$in": [ObjectId(pid) for pid in project_ids]},
            "updated_at": {"$gt": since_dt}
        }))
        recently_updated_project_ids = [str(p["_id"]) for p in recently_updated_projects]
        
        if recently_updated_project_ids:
            student_query = {
                "project_id": {"$in": project_ids},
                "$or": [
                    {"updated_at": {"$gt": since_dt}},
                    {"project_id": {"$in": recently_updated_project_ids}}
                ]
            }
        else:
            student_query["updated_at"] = {"$gt": since_dt}"""

if old_pull in content:
    content = content.replace(old_pull, new_pull)
    with open("routes/sync.py", "w") as f:
        f.write(content)
    print("Patched successfully")
else:
    print("Could not find block to patch")
