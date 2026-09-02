from database import get_db
from bson import ObjectId
import sys

def run_migration(dry_run=True):
    db = get_db()
    mock_project_id = "60d5ec34b0d87a4190c7bfa4"
    
    # 1. Find orphaned students
    orphaned_students = list(db.students.find({"project_id": mock_project_id}))
    if not orphaned_students:
        print("No orphaned students found.")
        return

    # 2. Group by school_id
    grouped = {}
    for s in orphaned_students:
        sid = s.get("school_id")
        if not sid:
            continue
        if sid not in grouped:
            grouped[sid] = []
        grouped[sid].append(s)
        
    print(f"--- DRY RUN REPORT ---" if dry_run else f"--- ACTUAL MIGRATION REPORT ---")
    
    can_migrate = True
    migrations = []
    
    # 3. For each school_id, find valid project
    for sid, students in grouped.items():
        projects = list(db.projects.find({
            "school_id": sid, 
            "_id": {"$ne": ObjectId(mock_project_id)}
        }))
        
        if len(projects) == 0:
            print(f"[ERROR] School {sid}: No valid projects found.")
            can_migrate = False
        elif len(projects) > 1:
            print(f"[ERROR] School {sid}: Ambiguous! Found {len(projects)} valid projects.")
            can_migrate = False
        else:
            target = projects[0]
            print(f"School ID: {sid}")
            print(f"Affected Student Count: {len(students)}")
            print(f"Old Project ID: {mock_project_id}")
            print(f"Target Project MongoDB _id: {str(target['_id'])}")
            print(f"Target Business project_id: {target.get('project_id')}")
            print(f"Target Project Name: {target.get('name')}")
            print(f"Academic Year: {target.get('academic_year')}")
            print(f"Project Status: {target.get('status')}")
            print("-" * 40)
            
            migrations.append({
                "school_id": sid,
                "target_id": str(target["_id"]),
                "count": len(students)
            })
            
    if dry_run:
        if not can_migrate:
            print("Dry run FAILED due to errors. Will not proceed.")
            sys.exit(1)
        else:
            print("Dry run passed successfully. Ready for actual migration.")
            sys.exit(0)
            
    # 4. Execute Migration
    if can_migrate:
        total_updated = 0
        for m in migrations:
            result = db.students.update_many(
                {"project_id": mock_project_id, "school_id": m["school_id"]},
                {"$set": {"project_id": m["target_id"]}}
            )
            total_updated += result.modified_count
            print(f"Migrated {result.modified_count} students for school {m['school_id']}")
        print(f"Total records changed: {total_updated}")

if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'dry'
    run_migration(dry_run=(mode != 'live'))
