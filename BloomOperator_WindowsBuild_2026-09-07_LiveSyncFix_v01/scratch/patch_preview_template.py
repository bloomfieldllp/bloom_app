import re

with open("templates/school/import_preview.html", "r") as f:
    content = f.read()
    
# We will inject the new intelligent summary right above the issues details box.
injection = """
        <!-- Intelligent Parsing Summary -->
        <div style="background-color: #f0f7ff; padding: 1rem; border-radius: 8px; margin-bottom: 1.5rem; text-align: left; border: 1px solid #d0e3ff;">
            <h4 style="margin: 0 0 0.5rem 0; color: #0056b3; font-size: 0.9rem; font-weight: 700;">Intelligent Parsing Results</h4>
            <ul style="margin: 0; padding-left: 1.25rem; font-size: 0.8rem; color: #333; line-height: 1.4;">
                <li><strong>Blocks detected:</strong> {{ report.blocks_detected }}</li>
                <li><strong>Standard fields detected:</strong> {{ report.detected_standard_fields | join(', ') }}</li>
                {% if report.new_custom_fields %}
                <li style="color: #008000;"><strong>New custom fields discovered:</strong>
                    {% for k, v in report.new_custom_fields.items() %}{{ v }}{% if not loop.last %}, {% endif %}{% endfor %}
                </li>
                {% endif %}
            </ul>
        </div>
"""

content = content.replace("<!-- Issues details box -->", injection + "\n        <!-- Issues details box -->")

# Remove mapping_json hidden input
content = content.replace('<input type="hidden" name="mapping_json" value="{{ mapping_json }}">', '')

with open("templates/school/import_preview.html", "w") as f:
    f.write(content)
