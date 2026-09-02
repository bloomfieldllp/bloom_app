from database import get_db
db = get_db()
kharadpada_id = "6a9260be40c415f29747b9e0"
project_id = "6a9577c02a2df71904770996"
old_project_id = "60d5ec34b0d87a4190c7bfa4"
print(f"Total students for Kharadpada PS: {db.students.count_documents({'school_id': kharadpada_id})}")
print(f"Total students mapped to NEW project: {db.students.count_documents({'school_id': kharadpada_id, 'project_id': project_id})}")
print(f"Total students mapped to OLD project: {db.students.count_documents({'school_id': kharadpada_id, 'project_id': old_project_id})}")
print(f"Total students mapped to OLD project across ALL schools: {db.students.count_documents({'project_id': old_project_id})}")
