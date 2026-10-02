with open("templates/operator/session.html", "r") as f:
    content = f.read()

bad_snippet = """<div id="no-active-student-card" style="padding: 2.5rem; text-align: center; border: 2px dashed var(--border-color); border-radius: 12px; color: var(--text-secondary); font-size: 0.9rem;">
                <svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="color: var(--text-secondary); margin-bottom: 0.5rem;"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
                <div style="font-weight: 700; color: var(--text-primary);">No Student Active</div>"""

good_snippet = """<div id="no-active-student-card" style="padding: 1.5rem; text-align: center; border: 2px dashed var(--border-color); border-radius: 12px; color: var(--text-secondary); font-size: 0.9rem; margin-bottom: 1rem;">
                <svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="color: var(--text-secondary); margin-bottom: 0.5rem;"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
                <div style="font-weight: 700; color: var(--text-primary);">No Student Active</div>
                <div>Select a student from the directory to begin capturing.</div>
            </div>"""

content = content.replace(bad_snippet, good_snippet)

# Also fix the residual text that was left behind in the right panel!
content = content.replace("\n                Select a student from the directory to begin monitoring photo directory.\n            </div>\n", "")

with open("templates/operator/session.html", "w") as f:
    f.write(content)
