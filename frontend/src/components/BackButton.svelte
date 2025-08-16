<script lang="ts">
    import { ArrowLeft } from 'lucide-svelte';
    import { goto } from '$app/navigation';

    export let href: string = '/';
    export let title: string = 'Back';
</script>

<button
    on:click={() => goto(href)}
    class="back-button"
    data-testid="back-button"
    {title}
>
    <ArrowLeft size={24} />
</button>

<style>
    .back-button {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 40px;
        height: 40px;
        padding: 8px;
        background-color: rgba(255, 255, 255, 0.9);
        color: #374151;
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        cursor: pointer;
        transition: all 0.2s ease;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
    }
    
    .back-button:hover {
        background-color: #f9fafb;
        border-color: #d1d5db;
        transform: translateY(-1px);
        box-shadow: 0 4px 8px rgba(0, 0, 0, 0.15);
    }
    
    .back-button:active {
        transform: translateY(0);
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
    }
</style>