<svelte:head>
	<title>Contact - Hillview</title>
</svelte:head>

<script lang="ts">
    import { Mail, Send, MessageSquare, User, CheckCircle, AlertCircle } from 'lucide-svelte';
    import StandardHeaderWithAlert from '../../components/StandardHeaderWithAlert.svelte';
    import StandardBody from '../../components/StandardBody.svelte';
    import { http } from '$lib/http';
    import { auth } from '$lib/auth.svelte';

    let contact = '';
    let message = '';
    let submitting = false;
    let submitted = false;
    let error = '';

    async function handleSubmit() {
        if (!contact.trim() || !message.trim()) {
            error = 'Please fill in all fields';
            return;
        }

        if (message.trim().length < 10) {
            error = 'Message must be at least 10 characters long';
            return;
        }

        submitting = true;
        error = '';

        try {
            const response = await http.post('/contact', {
                contact: contact.trim(),
                message: message.trim()
            });

            if (response.ok) {
                submitted = true;
                contact = '';
                message = '';
            } else {
                const errorData = await response.json().catch(() => ({ detail: 'Failed to send message' }));
                error = errorData.detail || 'Failed to send message';
            }
        } catch (e) {
            error = 'Network error. Please try again later.';
        } finally {
            submitting = false;
        }
    }

    function resetForm() {
        submitted = false;
        error = '';
    }
</script>

<StandardHeaderWithAlert
    title="Contact Us"
    showMenuButton={true}
    fallbackHref="/"
/>

<StandardBody>
    <div class="contact-container">
        <header class="contact-header">
            <div class="contact-icon">
                <Mail size={32} />
            </div>
            <h1>Get in Touch</h1>
            <p class="contact-tagline">
                We'd love to hear from you! Whether you have questions, feedback, or suggestions,
                feel free to reach out.
            </p>
        </header>

        {#if submitted}
            <div class="success-message">
                <CheckCircle size={24} />
                <h2>Message Sent!</h2>
                <p>Thank you for contacting us. We'll get back to you as soon as possible.</p>
                <button class="btn-secondary" on:click={resetForm}>
                    Send Another Message
                </button>
            </div>
        {:else}
            <div class="contact-form-container">
                <form on:submit|preventDefault={handleSubmit} class="contact-form">
                    <div class="form-group">
                        <label for="contact">
                            <User size={16} />
                            Email or Contact Information
                        </label>
                        <input
                            id="contact"
                            type="text"
                            bind:value={contact}
                            placeholder="your.email@example.com or other contact method"
                            required
                            disabled={submitting}
                        />
                        <small class="form-help">
                            We'll use this to get back to you. Email address, username, or other contact method.
                        </small>
                    </div>

                    <div class="form-group">
                        <label for="message">
                            <MessageSquare size={16} />
                            Message
                        </label>
                        <textarea
                            id="message"
                            bind:value={message}
                            placeholder="Tell us about your question, feedback, or suggestion..."
                            rows="6"
                            required
                            disabled={submitting}
                        ></textarea>
                        <small class="form-help">
                            Please provide as much detail as possible to help us assist you better.
                        </small>
                    </div>

                    {#if error}
                        <div class="error-message">
                            <AlertCircle size={16} />
                            {error}
                        </div>
                    {/if}

                    <div class="form-actions">
                        <button
                            type="submit"
                            class="btn-primary"
                            disabled={submitting || !contact.trim() || !message.trim()}
                        >
                            {#if submitting}
                                Sending...
                            {:else}
                                <Send size={16} />
                                Send Message
                            {/if}
                        </button>
                    </div>

                    {#if $auth.user}
                        <div class="user-info">
                            <small>
                                Sending as: <strong>{$auth.user.username}</strong>
                            </small>
                        </div>
                    {:else}
                        <div class="guest-info">
                            <small>
                                You're sending this message as a guest.
                                <a href="/login">Log in</a> if you have an account.
                            </small>
                        </div>
                    {/if}
                </form>

                <div class="contact-info">
                    <h3>Other Ways to Reach Us</h3>
                    <div class="contact-methods">
                        <div class="contact-method">
                            <strong>GitHub Issues</strong>
                            <p>Report bugs or request features on our GitHub repository</p>
                            <a href="https://github.com/koo5/hillview/issues" target="_blank" rel="noopener noreferrer">
                                Open an Issue
                            </a>
                        </div>
                        <div class="contact-method">
                            <strong>Community</strong>
                            <p>Join discussions and connect with other users</p>
                            <span class="coming-soon">Coming Soon</span>
                        </div>
                    </div>
                </div>
            </div>
        {/if}
    </div>
</StandardBody>

<style>
    .contact-container {
        max-width: 800px;
        margin: 0 auto;
        padding: 0 16px;
    }

    .contact-header {
        text-align: center;
        margin-bottom: 48px;
    }

    .contact-icon {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 64px;
        height: 64px;
        background: linear-gradient(135deg, #dcfce7, #bbf7d0);
        border-radius: 16px;
        color: #15803d;
        margin-bottom: 16px;
    }

    .contact-header h1 {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f2937;
        margin: 0 0 16px 0;
    }

    .contact-tagline {
        font-size: 1.125rem;
        color: #4b5563;
        margin: 0;
        max-width: 600px;
        margin-left: auto;
        margin-right: auto;
    }

    .contact-form-container {
        display: grid;
        grid-template-columns: 1fr 300px;
        gap: 48px;
        align-items: start;
    }

    .contact-form {
        background: rgba(255, 255, 255, 0.8);
        padding: 32px;
        border-radius: 16px;
        backdrop-filter: blur(10px);
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }

    .form-group {
        margin-bottom: 24px;
    }

    .form-group label {
        display: flex;
        align-items: center;
        gap: 8px;
        font-weight: 600;
        color: #374151;
        margin-bottom: 8px;
        font-size: 0.875rem;
    }

    .form-group input,
    .form-group textarea {
        width: 100%;
        padding: 12px 16px;
        border: 1px solid #d1d5db;
        border-radius: 8px;
        font-size: 1rem;
        transition: border-color 0.2s ease, box-shadow 0.2s ease;
        background: white;
        resize: vertical;
    }

    .form-group input:focus,
    .form-group textarea:focus {
        outline: none;
        border-color: #4f46e5;
        box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.1);
    }

    .form-group input:disabled,
    .form-group textarea:disabled {
        background: #f9fafb;
        cursor: not-allowed;
        opacity: 0.7;
    }

    .form-help {
        display: block;
        margin-top: 4px;
        color: #6b7280;
        font-size: 0.75rem;
    }

    .form-actions {
        margin-bottom: 16px;
    }

    .btn-primary {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        background: #4f46e5;
        color: white;
        border: none;
        padding: 12px 24px;
        border-radius: 8px;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.2s ease;
        font-size: 1rem;
    }

    .btn-primary:hover:not(:disabled) {
        background: #3730a3;
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(79, 70, 229, 0.3);
    }

    .btn-primary:disabled {
        background: #9ca3af;
        cursor: not-allowed;
        transform: none;
        box-shadow: none;
    }

    .btn-secondary {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        background: white;
        color: #4f46e5;
        border: 1px solid #4f46e5;
        padding: 12px 24px;
        border-radius: 8px;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.2s ease;
        font-size: 1rem;
        text-decoration: none;
    }

    .btn-secondary:hover {
        background: #f9fafb;
        transform: translateY(-1px);
    }

    .success-message {
        text-align: center;
        background: rgba(255, 255, 255, 0.8);
        padding: 48px 32px;
        border-radius: 16px;
        backdrop-filter: blur(10px);
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }

    .success-message :global(svg) {
        color: #059669;
        margin-bottom: 16px;
    }

    .success-message h2 {
        font-size: 1.5rem;
        font-weight: 600;
        color: #1f2937;
        margin: 0 0 8px 0;
    }

    .success-message p {
        color: #4b5563;
        margin: 0 0 24px 0;
    }

    .error-message {
        display: flex;
        align-items: center;
        gap: 8px;
        background: #fef2f2;
        border: 1px solid #fecaca;
        color: #991b1b;
        padding: 12px 16px;
        border-radius: 8px;
        margin-bottom: 16px;
        font-size: 0.875rem;
    }

    .user-info,
    .guest-info {
        text-align: center;
        padding-top: 16px;
        border-top: 1px solid #e5e7eb;
    }

    .guest-info a {
        color: #4f46e5;
        text-decoration: none;
    }

    .guest-info a:hover {
        text-decoration: underline;
    }

    .contact-info {
        background: rgba(255, 255, 255, 0.8);
        padding: 32px;
        border-radius: 16px;
        backdrop-filter: blur(10px);
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        height: fit-content;
    }

    .contact-info h3 {
        font-size: 1.125rem;
        font-weight: 600;
        color: #1f2937;
        margin: 0 0 24px 0;
    }

    .contact-methods {
        display: flex;
        flex-direction: column;
        gap: 24px;
    }

    .contact-method {
        border-bottom: 1px solid #e5e7eb;
        padding-bottom: 16px;
    }

    .contact-method:last-child {
        border-bottom: none;
        padding-bottom: 0;
    }

    .contact-method strong {
        display: block;
        color: #1f2937;
        margin-bottom: 4px;
        font-size: 0.875rem;
    }

    .contact-method p {
        color: #6b7280;
        margin: 0 0 8px 0;
        font-size: 0.75rem;
    }

    .contact-method a {
        color: #4f46e5;
        text-decoration: none;
        font-size: 0.75rem;
        font-weight: 500;
    }

    .contact-method a:hover {
        text-decoration: underline;
    }

    .coming-soon {
        color: #9ca3af;
        font-size: 0.75rem;
        font-style: italic;
    }

    /* Responsive design */
    @media (max-width: 768px) {
        .contact-header h1 {
            font-size: 2rem;
        }

        .contact-form-container {
            grid-template-columns: 1fr;
            gap: 32px;
        }

        .contact-form,
        .contact-info {
            padding: 24px;
        }
    }
</style>