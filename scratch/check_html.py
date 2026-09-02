from bs4 import BeautifulSoup

with open("templates/operator/session.html", "r") as f:
    soup = BeautifulSoup(f.read(), "html.parser")

left_panel = soup.select_one(".panel:nth-of-type(1)")
right_panel = soup.select_one(".panel:nth-of-type(2)")

if not left_panel: print("No Left Panel")
if not right_panel: print("No Right Panel")

if left_panel:
    active_panel = left_panel.select_one("#active-student-panel")
    no_active = left_panel.select_one("#no-active-student-card")
    search_card = left_panel.select_one(".card:has(#session-search-input)")
    
    if active_panel: print("Active panel is in left panel")
    if no_active: print("No active card is in left panel")
    if search_card: print("Search card is in left panel")

if right_panel:
    alert_console = right_panel.select_one("#alert-console-wrapper")
    if alert_console: print("Alert console is in right panel")

