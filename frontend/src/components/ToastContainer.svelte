<script lang="ts">
    import { toasts, removeToast, type Toast } from '$lib/toast.svelte';
    import { X } from 'lucide-svelte';

    function handleDismiss(toastId: string) {
        removeToast(toastId);
    }

    function getToastClass(type: Toast['type']): string {
        switch (type) {
            case 'error': return 'toast-error';
            case 'warning': return 'toast-warning';
            case 'success': return 'toast-success';
            case 'info': 
            default: return 'toast-info';
        }
    }
</script>

<div class="toast-container">
    {#each $toasts as toast (toast.id)}
        <div class="toast {getToastClass(toast.type)}">
            <div class="toast-content">
                <span class="toast-message">{toast.message}</span>
                <button 
                    class="toast-dismiss" 
                    on:click={() => handleDismiss(toast.id)}
                    data-testid="toast-dismiss-{toast.id}"
                >
                    <X size={16} />
                </button>
            </div>
        </div>
    {/each}
</div>

<style>
    .toast-container {
        position: fixed;
        top: 1rem;
        right: 1rem;
        z-index: 1000;
        display: flex;
        flex-direction: column;
        gap: 0.5rem;
        max-width: 400px;
    }

    .toast {
        border-radius: 0.5rem;
        padding: 1rem;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        animation: slide-in 0.3s ease-out;
        border-left: 4px solid;
    }

    .toast-content {
        display: flex;
        align-items: flex-start;
        gap: 0.75rem;
    }

    .toast-message {
        flex: 1;
        font-size: 0.9rem;
        line-height: 1.4;
    }

    .toast-dismiss {
        background: none;
        border: none;
        cursor: pointer;
        padding: 0;
        display: flex;
        align-items: center;
        opacity: 0.7;
        transition: opacity 0.2s;
        flex-shrink: 0;
    }

    .toast-dismiss:hover {
        opacity: 1;
    }

    .toast-error {
        background: #fef2f2;
        border-left-color: #ef4444;
        color: #991b1b;
    }

    .toast-warning {
        background: #fffbeb;
        border-left-color: #f59e0b;
        color: #92400e;
    }

    .toast-success {
        background: #f0fdf4;
        border-left-color: #22c55e;
        color: #166534;
    }

    .toast-info {
        background: #eff6ff;
        border-left-color: #3b82f6;
        color: #1e40af;
    }

    @keyframes slide-in {
        from {
            transform: translateX(100%);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }
</style>