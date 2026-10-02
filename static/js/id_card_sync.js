/**
 * Bloom ID Card Offline-Safe Synchronization Manager
 * 
 * Provides durable local persistence via IndexedDB / localStorage,
 * immediate optimistic UI updates, auto-retry on reconnection,
 * and clear visual sync feedback badges.
 */

class IdCardSyncManager {
    constructor() {
        this.storageKey = 'bloom_id_card_pending_queue';
        this.isSyncing = false;
        this.syncListeners = [];
        this.statusBadgeEl = null;
        
        // Listen to online / offline events
        window.addEventListener('online', () => this.handleNetworkChange(true));
        window.addEventListener('offline', () => this.handleNetworkChange(false));
        
        // Auto sync every 15s when online
        setInterval(() => {
            if (navigator.onLine && this.getQueue().length > 0) {
                this.processQueue();
            }
        }, 15000);
    }

    getQueue() {
        try {
            const data = localStorage.getItem(this.storageKey);
            return data ? JSON.parse(data) : [];
        } catch (e) {
            console.error('Failed to read sync queue from storage:', e);
            return [];
        }
    }

    saveQueue(queue) {
        try {
            localStorage.setItem(this.storageKey, JSON.stringify(queue));
            this.notifyListeners(queue);
            this.updateBadgeState();
        } catch (e) {
            console.error('Failed to save sync queue to storage:', e);
        }
    }

    enqueue(operation) {
        const queue = this.getQueue();
        const opId = operation.id || 'op_' + Date.now() + '_' + Math.random().toString(36).substring(2, 9);
        const op = {
            id: opId,
            school_id: operation.school_id,
            card_id: operation.card_id,
            class_name: operation.class_name,
            operation_type: operation.operation_type, // 'VERIFY' | 'CORRECTION'
            payload: operation.payload,
            photo_file_base64: operation.photo_file_base64 || null,
            photo_filename: operation.photo_filename || null,
            created_at: new Date().toISOString(),
            retry_count: 0,
            sync_status: 'PENDING', // 'PENDING' | 'SYNCING' | 'FAILED'
            last_error: null
        };

        // If an operation already exists for this card_id in the queue, update it
        const existingIdx = queue.findIndex(item => item.card_id === op.card_id && item.operation_type === op.operation_type);
        if (existingIdx >= 0) {
            queue[existingIdx] = op;
        } else {
            queue.push(op);
        }

        this.saveQueue(queue);
        
        // If online, immediately attempt synchronization
        if (navigator.onLine) {
            this.processQueue();
        } else {
            this.updateBadgeState('SAVED_OFFLINE');
        }

        return op;
    }

    async processQueue() {
        if (this.isSyncing) return;
        const queue = this.getQueue();
        if (queue.length === 0) {
            this.updateBadgeState('IDLE');
            return;
        }

        this.isSyncing = true;
        this.updateBadgeState('SYNCING');

        const remainingQueue = [];

        for (const op of queue) {
            try {
                let success = false;
                if (op.operation_type === 'VERIFY') {
                    success = await this.sendVerifyRequest(op);
                } else if (op.operation_type === 'CORRECTION') {
                    success = await this.sendCorrectionRequest(op);
                }

                if (!success) {
                    op.retry_count = (op.retry_count || 0) + 1;
                    op.sync_status = 'FAILED';
                    remainingQueue.push(op);
                }
            } catch (err) {
                console.error(`Error syncing operation ${op.id}:`, err);
                op.retry_count = (op.retry_count || 0) + 1;
                op.sync_status = 'FAILED';
                op.last_error = err.message || 'Network error';
                remainingQueue.push(op);
            }
        }

        this.saveQueue(remainingQueue);
        this.isSyncing = false;

        if (remainingQueue.length === 0) {
            this.updateBadgeState('SYNCED');
            setTimeout(() => {
                if (this.getQueue().length === 0) {
                    this.updateBadgeState('IDLE');
                }
            }, 3000);
        } else {
            this.updateBadgeState('RETRYING');
        }
    }

    async sendVerifyRequest(op) {
        const formData = new FormData();
        formData.append('card_id', op.card_id);
        formData.append('operation_id', op.id);

        const res = await fetch('/school/verification/verify', {
            method: 'POST',
            body: formData,
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        });

        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || 'Verification failed on server');
        }
        return true;
    }

    async sendCorrectionRequest(op) {
        const formData = new FormData();
        formData.append('card_id', op.card_id);
        formData.append('operation_id', op.id);
        formData.append('photo_wrong', op.payload.photo_wrong ? 'true' : 'false');
        
        // Append all field values
        for (const [k, v] of Object.entries(op.payload.fields || {})) {
            if (v !== undefined && v !== null) {
                formData.append(k, v);
            }
        }

        // Handle replacement photo file if stored as base64 in offline queue
        if (op.photo_file_base64 && op.photo_filename) {
            const blob = this.base64ToBlob(op.photo_file_base64);
            formData.append('replacement_photo', blob, op.photo_filename);
        }

        const res = await fetch('/school/verification/edit', {
            method: 'POST',
            body: formData,
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        });

        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || 'Correction submission failed on server');
        }
        return true;
    }

    handleNetworkChange(isOnline) {
        console.log(`Network status changed: ${isOnline ? 'Online' : 'Offline'}`);
        if (isOnline) {
            this.processQueue();
        } else {
            this.updateBadgeState('OFFLINE');
        }
    }

    base64ToBlob(base64Data) {
        const parts = base64Data.split(';base64,');
        const contentType = parts[0].split(':')[1] || 'image/jpeg';
        const raw = window.atob(parts[1] || parts[0]);
        const rawLength = raw.length;
        const uInt8Array = new Uint8Array(rawLength);
        for (let i = 0; i < rawLength; ++i) {
            uInt8Array[i] = raw.charCodeAt(i);
        }
        return new Blob([uInt8Array], { type: contentType });
    }

    onQueueChange(callback) {
        this.syncListeners.push(callback);
    }

    notifyListeners(queue) {
        this.syncListeners.forEach(cb => {
            try { cb(queue); } catch (e) {}
        });
    }

    setFeedbackElement(element) {
        this.statusBadgeEl = element;
        this.updateBadgeState();
    }

    updateBadgeState(forceState = null) {
        if (!this.statusBadgeEl) return;

        const queue = this.getQueue();
        let state = forceState;

        if (!state) {
            if (!navigator.onLine) {
                state = queue.length > 0 ? 'SAVED_OFFLINE' : 'OFFLINE';
            } else if (this.isSyncing) {
                state = 'SYNCING';
            } else if (queue.length > 0) {
                state = 'SAVED_OFFLINE';
            } else {
                state = 'IDLE';
            }
        }

        const el = this.statusBadgeEl;
        el.style.display = 'inline-flex';
        el.className = 'sync-status-badge';

        switch (state) {
            case 'SAVED_OFFLINE':
                el.innerHTML = '<span class="sync-dot sync-dot-warning"></span> Saved locally — waiting for internet';
                el.style.backgroundColor = '#fef3c7';
                el.style.color = '#92400e';
                el.style.border = '1px solid #fde68a';
                break;
            case 'SYNCING':
                el.innerHTML = '<span class="sync-spinner"></span> Syncing with server...';
                el.style.backgroundColor = '#dbeafe';
                el.style.color = '#1e40af';
                el.style.border = '1px solid #bfdbfe';
                break;
            case 'SYNCED':
                el.innerHTML = '<span class="sync-dot sync-dot-success"></span> All changes synced';
                el.style.backgroundColor = '#dcfce7';
                el.style.color = '#166534';
                el.style.border = '1px solid #bbf7d0';
                break;
            case 'RETRYING':
                el.innerHTML = `<span class="sync-dot sync-dot-danger"></span> Sync failed — retrying (${queue.length} pending)`;
                el.style.backgroundColor = '#fee2e2';
                el.style.color = '#991b1b';
                el.style.border = '1px solid #fecaca';
                break;
            case 'OFFLINE':
                el.innerHTML = '<span class="sync-dot sync-dot-muted"></span> Working offline';
                el.style.backgroundColor = '#f3f4f6';
                el.style.color = '#4b5563';
                el.style.border = '1px solid #e5e7eb';
                break;
            case 'IDLE':
            default:
                el.innerHTML = '<span class="sync-dot sync-dot-success"></span> Synced';
                el.style.backgroundColor = '#f9fafb';
                el.style.color = '#6b7280';
                el.style.border = '1px solid #e5e7eb';
                break;
        }
    }
}

// Global instance
window.idCardSync = new IdCardSyncManager();
