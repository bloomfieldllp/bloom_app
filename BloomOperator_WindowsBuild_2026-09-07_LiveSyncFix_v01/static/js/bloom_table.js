document.addEventListener('DOMContentLoaded', () => {
    enhanceAllTables();
});

document.addEventListener('htmx:afterOnLoad', () => {
    enhanceAllTables();
});

function enhanceAllTables() {
    const tables = document.querySelectorAll('table.enhanced-table');
    tables.forEach((table, index) => {
        enhanceTable(table, index);
    });
}

function enhanceTable(table, tableIndex) {
    if (table.dataset.enhanced === "true") return;
    table.dataset.enhanced = "true";
    
    // Ensure table is inside a table-container
    let tableContainer = table.parentElement;
    if (!tableContainer || !tableContainer.classList.contains('table-container')) {
        const tempContainer = document.createElement('div');
        tempContainer.className = 'table-container';
        table.parentNode.insertBefore(tempContainer, table);
        tempContainer.appendChild(table);
        tableContainer = tempContainer;
    }
    
    // Locate or create table-toolbar
    const cardContainer = table.closest('.card');
    let toolbar = cardContainer ? cardContainer.querySelector('.table-toolbar') : null;
    let searchInput = null;
    let actionsWrapper = null;
    
    if (toolbar) {
        // Reuse existing search input if present
        searchInput = toolbar.querySelector('.bloom-search-input') || toolbar.querySelector('input[type="text"]');
        actionsWrapper = toolbar.querySelector('.table-actions');
    } else {
        // Create wrapper to hold toolbar + tableContainer
        const grandParent = tableContainer.parentElement;
        const wrapper = document.createElement('div');
        wrapper.className = 'enhanced-table-wrapper';
        wrapper.style.display = 'flex';
        wrapper.style.flexDirection = 'column';
        wrapper.style.gap = '1rem';
        wrapper.style.width = '100%';
        
        grandParent.insertBefore(wrapper, tableContainer);
        wrapper.appendChild(tableContainer);
        
        // Create Toolbar
        toolbar = document.createElement('div');
        toolbar.className = 'table-toolbar';
        toolbar.style.display = 'flex';
        toolbar.style.justifyContent = 'space-between';
        toolbar.style.alignItems = 'center';
        toolbar.style.gap = '1rem';
        toolbar.style.flexWrap = 'wrap';
        toolbar.style.width = '100%';
        toolbar.style.marginBottom = '1.25rem';
        
        // Create Search wrapper if not explicitly disabled
        if (table.dataset.noSearch === "true") {
            toolbar.style.justifyContent = 'flex-end';
        } else {
            const searchWrapper = document.createElement('div');
            searchWrapper.style.position = 'relative';
            searchWrapper.style.flex = '1';
            searchWrapper.style.minWidth = '250px';
            searchWrapper.style.maxWidth = '400px';
            searchWrapper.style.display = 'flex';
            searchWrapper.style.alignItems = 'center';
            
            searchInput = document.createElement('input');
            searchInput.type = 'text';
            searchInput.className = 'form-control bloom-search-input';
            searchInput.placeholder = 'Search table rows...';
            searchInput.style.width = '100%';
            searchWrapper.appendChild(searchInput);
            
            toolbar.appendChild(searchWrapper);
        }
        
        // Create Actions Wrapper
        actionsWrapper = document.createElement('div');
        actionsWrapper.className = 'table-actions';
        actionsWrapper.style.position = 'relative';
        toolbar.appendChild(actionsWrapper);
        
        wrapper.insertBefore(toolbar, tableContainer);
    }
    
    // Bind search filtering logic
    if (searchInput) {
        searchInput.addEventListener('input', () => {
            const query = searchInput.value.toLowerCase();
            const rows = table.querySelectorAll('tbody tr');
            rows.forEach(row => {
                const text = row.textContent.toLowerCase();
                row.style.display = text.includes(query) ? '' : 'none';
            });
        });
    }
    
    // Set up Column Selector Popover
    if (actionsWrapper) {
        // Clear any existing column selector elements to prevent duplicates on HTMX reloads
        const existingBtn = actionsWrapper.querySelector('.column-selector-btn');
        const existingPopover = actionsWrapper.querySelector('.column-selector-popover');
        if (existingBtn) existingBtn.remove();
        if (existingPopover) existingPopover.remove();
        
        // Create Column Selector Button
        const selectBtn = document.createElement('button');
        selectBtn.type = 'button';
        selectBtn.className = 'btn btn-secondary column-selector-btn';
        selectBtn.style.display = 'inline-flex';
        selectBtn.style.alignItems = 'center';
        selectBtn.style.gap = '8px';
        selectBtn.style.border = '1px solid var(--border-color)';
        selectBtn.style.backgroundColor = 'var(--card-bg)';
        selectBtn.style.color = 'var(--brand-dark)';
        selectBtn.style.padding = '8px 14px';
        selectBtn.style.borderRadius = '10px';
        selectBtn.style.cursor = 'pointer';
        selectBtn.style.fontSize = '13px';
        selectBtn.style.fontWeight = '600';
        selectBtn.innerHTML = `
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="color: var(--brand-primary);"><rect width="18" height="18" x="3" y="3" rx="2"/><path d="M9 3v18"/><path d="M15 3v18"/></svg>
            Columns
        `;
        actionsWrapper.appendChild(selectBtn);
        
        // Create Popover Container
        const popover = document.createElement('div');
        popover.className = 'column-selector-popover card';
        
        const popoverTitle = document.createElement('div');
        popoverTitle.style.fontWeight = '700';
        popoverTitle.style.fontSize = '0.8rem';
        popoverTitle.style.textTransform = 'uppercase';
        popoverTitle.style.color = 'var(--text-secondary)';
        popoverTitle.style.borderBottom = '1px solid var(--border-color)';
        popoverTitle.style.paddingBottom = '0.5rem';
        popoverTitle.style.marginBottom = '0.5rem';
        popoverTitle.textContent = 'Display Columns';
        popover.appendChild(popoverTitle);
        
        const headers = table.querySelectorAll('thead th');
        headers.forEach((th, colIndex) => {
            const labelText = th.textContent.trim();
            if (!labelText) return;
            
            const label = document.createElement('label');
            
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.checked = true;
            
            checkbox.addEventListener('change', () => {
                const displayValue = checkbox.checked ? '' : 'none';
                th.style.display = displayValue;
                const rows = table.querySelectorAll('tbody tr');
                rows.forEach(row => {
                    const cells = row.querySelectorAll('td');
                    if (cells[colIndex]) {
                        cells[colIndex].style.display = displayValue;
                    }
                });
            });
            
            label.appendChild(checkbox);
            label.appendChild(document.createTextNode(labelText));
            popover.appendChild(label);
        });
        
        // Bind click event to toggle popover
        selectBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            const isOpen = popover.style.display === 'flex';
            
            // Close other open popovers first
            document.querySelectorAll('.column-selector-popover').forEach(p => p.style.display = 'none');
            
            popover.style.display = isOpen ? 'none' : 'flex';
        });
        
        // Prevent clicks inside the popover from closing it
        popover.addEventListener('click', (e) => {
            e.stopPropagation();
        });
        
        // Append popover to actions wrapper
        actionsWrapper.appendChild(popover);
    }
}

// Global click event to close popover when clicking outside
document.addEventListener('click', () => {
    document.querySelectorAll('.column-selector-popover').forEach(popover => {
        popover.style.display = 'none';
    });
});
