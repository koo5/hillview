<script lang="ts">
    import { currentAlert, removeAlert, fadeAlert, unfadeAlert, alerts } from '$lib/alertSystem.svelte';
    import { X, RotateCcw, AlertTriangle, CheckCircle, Info, AlertCircle } from 'lucide-svelte';
    import { createEventDispatcher } from 'svelte';

    export let position: 'header' | 'main' = 'header';

    const dispatch = createEventDispatcher();

    function handleClick(alert: any) {
        if (alert.faded) {
            unfadeAlert(alert.id);
        } else {
            fadeAlert(alert.id);
        }
    }

    function handleDismiss(alert: any, event: Event) {
        event.stopPropagation();
        removeAlert(alert.id);
    }

    function handleRetry(alert: any, event: Event) {
        event.stopPropagation();
        if (alert.onRetry) {
            alert.onRetry();
        }
    }

    function handleAction(action: any, event: Event) {
        event.stopPropagation();
        action.action();
    }

    function getIcon(type: string) {
        switch (type) {
            case 'error': return AlertTriangle;
            case 'warning': return AlertCircle;
            case 'success': return CheckCircle;
            case 'info':
            default: return Info;
        }
    }

    function getAlertClass(type: string): string {
        switch (type) {
            case 'error': return 'alert-error';
            case 'warning': return 'alert-warning';
            case 'success': return 'alert-success';
            case 'info':
            default: return 'alert-info';
        }
    }

    function getActionButtonClass(style?: string): string {
        switch (style) {
            case 'primary': return 'action-primary';
            case 'danger': return 'action-danger';
            case 'secondary':
            default: return 'action-secondary';
        }
    }

    // Count of pending alerts for indicator
    $: pendingCount = $alerts.filter(a => a.id !== $currentAlert?.id && !a.faded).length;
</script>

{#if $currentAlert}
    <div
        class="alert-area {position} {getAlertClass($currentAlert.type)}"
        class:faded={$currentAlert.faded}
        on:click={() => handleClick($currentAlert)}
        on:keydown={(e) => e.key === 'Enter' && handleClick($currentAlert)}
        role="button"
        tabindex="0"
        data-testid="alert-area-{$currentAlert.id}"
    >
        <div class="alert-content">
            <div class="alert-main">
                <div class="alert-icon">
                    <svelte:component this={getIcon($currentAlert.type)} size={20} />
                </div>

                <div class="alert-text">
                    <span class="alert-message">{$currentAlert.message}</span>
                    {#if pendingCount > 0}
                        <span class="alert-count">+{pendingCount} more</span>
                    {/if}
                </div>
            </div>

            <div class="alert-actions">
                {#if $currentAlert.retryable && $currentAlert.onRetry}
                    <button
                        class="alert-button retry-button"
                        on:click={(e) => handleRetry($currentAlert, e)}
                        aria-label="Retry"
                        data-testid="alert-retry-{$currentAlert.id}"
                    >
                        <RotateCcw size={16} />
                    </button>
                {/if}

                {#if $currentAlert.actions}
                    {#each $currentAlert.actions as action}
                        <button
                            class="alert-action-button {getActionButtonClass(action.style)}"
                            on:click={(e) => handleAction(action, e)}
                            data-testid="alert-action-{action.label.toLowerCase()}"
                        >
                            {action.label}
                        </button>
                    {/each}
                {/if}

                {#if $currentAlert.dismissible !== false}
                    <button
                        class="alert-button dismiss-button"
                        on:click={(e) => handleDismiss($currentAlert, e)}
                        aria-label="Dismiss"
                        data-testid="alert-dismiss-{$currentAlert.id}"
                    >
                        <X size={16} />
                    </button>
                {/if}
            </div>
        </div>
    </div>
{/if}

<style>
    .alert-area {
        /*background: rgba(255, 255, 255, 0.15);*/
        border-radius: 8px;
        padding: 12px 16px;
        margin: 8px 0;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
        border-left: 4px solid;
        cursor: pointer;
        transition: all 0.3s ease;
        animation: slide-in 0.3s ease-out;
        border-bottom: 1px solid #e5e7eb;
		z-index: 30002;
    }

    .alert-area.faded {
        opacity: 0.6;
        background: rgba(249, 250, 251, 0.8);
    }

    .alert-area.header {
        position: fixed;
        top: 50px; /* Below StandardHeader */
        left: 0;
        right: 0;
        margin: 0;
        border-radius: 0;
        border-left: none;
        border-top: 4px solid;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        z-index: 30002; /* Above header but below overlays */
    }

    .alert-content {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
    }

    .alert-main {
        display: flex;
        align-items: center;
        gap: 12px;
        flex: 1;
        min-width: 0;
    }

    .alert-icon {
        display: flex;
        align-items: center;
        flex-shrink: 0;
    }

    .alert-text {
        flex: 1;
        min-width: 0;
    }

    .alert-message {
        font-size: 0.9rem;
        line-height: 1.4;
        display: block;
    }

    .alert-count {
        font-size: 0.75rem;
        opacity: 0.7;
        margin-left: 8px;
        font-weight: 500;
    }

    .alert-actions {
        display: flex;
        align-items: center;
        gap: 8px;
        flex-shrink: 0;
    }

    .alert-button {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 32px;
        height: 32px;
        background: none;
        border: 1px solid rgba(0, 0, 0, 0.1);
        border-radius: 6px;
        cursor: pointer;
        transition: all 0.2s ease;
        color: inherit;
    }

    .alert-button:hover {
        background: rgba(0, 0, 0, 0.05);
        transform: scale(1.05);
    }

    .alert-action-button {
        padding: 6px 12px;
        border: 1px solid rgba(0, 0, 0, 0.2);
        border-radius: 6px;
        background: white;
        cursor: pointer;
        font-size: 0.85rem;
        font-weight: 500;
        transition: all 0.2s ease;
    }

    .action-primary {
        background: #3b82f6;
        color: white;
        border-color: #3b82f6;
    }

    .action-primary:hover {
        background: #2563eb;
    }

    .action-danger {
        background: #ef4444;
        color: white;
        border-color: #ef4444;
    }

    .action-danger:hover {
        background: #dc2626;
    }

    .action-secondary:hover {
        background: #f3f4f6;
    }

    /* Alert type styling */
    .alert-error {
        background: #fef2f2;
        border-left-color: #ef4444;
        color: #991b1b;
    }

    .alert-error.header {
        border-top-color: #ef4444;
    }

    .alert-warning {
        background: #fffbeb;
        border-left-color: #f59e0b;
        color: #92400e;
    }

    .alert-warning.header {
        border-top-color: #f59e0b;
    }

    .alert-success {
        background: #f0fdf4;
        border-left-color: #22c55e;
        color: #166534;
    }

    .alert-success.header {
        border-top-color: #22c55e;
    }

    .alert-info {
        background: rgba(239, 246, 255, 0.55);
        border-left-color: #3b82f6;
        color: #1e40af;
    }

    .alert-info.header {
        border-top-color: #3b82f6;
    }

    @keyframes slide-in {
        from {
            transform: translateY(-100%);
            opacity: 0;
        }
        to {
            transform: translateY(0);
            opacity: 1;
        }
    }

    /* Responsive adjustments */
    @media (max-width: 640px) {
        .alert-area {
            padding: 10px 12px;
        }

        .alert-area.header {
            top: 56px; /* Below mobile StandardHeader */
        }

        .alert-content {
            gap: 8px;
        }

        .alert-main {
            gap: 8px;
        }

        .alert-message {
            font-size: 0.85rem;
        }

        .alert-button {
            width: 28px;
            height: 28px;
        }

        .alert-action-button {
            padding: 4px 8px;
            font-size: 0.8rem;
        }
    }
</style>
