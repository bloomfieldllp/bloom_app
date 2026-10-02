with open("services/local_db.py", "r") as f:
    content = f.read()

# We need to hook into get_schools, get_school, list_schools, etc. if they exist and return schools.
# Let's see what exists.
