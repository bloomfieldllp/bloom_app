import re

with open("templates/operator/session.html", "r") as f:
    content = f.read()

# 1. Extract active-student-panel and no-active-student-card
active_panel_regex = r'(<!-- Active Student Panel -->.*?</div>\s*</div>\s*</div>)'
no_active_card_regex = r'(<div id="no-active-student-card".*?</div>)'

m1 = re.search(active_panel_regex, content, re.DOTALL)
m2 = re.search(no_active_card_regex, content, re.DOTALL)

active_panel_html = m1.group(1)
no_active_card_html = m2.group(1)

# Remove them from the right panel
content = content.replace(active_panel_html, "")
content = content.replace(no_active_card_html, "")

# 2. Extract and remove storage-config-panel
storage_config_regex = r'(<!-- Storage Configuration -->.*?</form>\s*</div>)'
m3 = re.search(storage_config_regex, content, re.DOTALL)
storage_config_html = m3.group(1)
content = content.replace(storage_config_html, "")

# 3. Insert active panels above Search & Filter Card
search_filter_marker = "<!-- Search & Filter Card -->"
replacement = active_panel_html + "\n            " + no_active_card_html + "\n            <br>\n            " + search_filter_marker
content = content.replace(search_filter_marker, replacement)

with open("templates/operator/session.html", "w") as f:
    f.write(content)
